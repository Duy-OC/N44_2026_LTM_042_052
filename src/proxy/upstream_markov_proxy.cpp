#include "network.h"
#include "mavlink_codec.h"
#include "qos.h"
#include "emulator.h"
#include "time_utils.h"
#include <windows.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cerrno>
#include <cctype>
#include <deque>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <random>
#include <stdexcept>
#include <string>

namespace
{
struct Options
{
    Markov::Config markov;
    Markov::Config reverseMarkov;
    std::string runId;
    std::string scenario = "UPSTREAM";
    std::string outputDir;
    int sysid = 1;
    unsigned short px4ListenPort = 14551;
    unsigned short gatewaySourcePort = 14610;
    unsigned short gatewayPort = 14550;
    int measureSeconds = 60;
    bool measure = false;
    double flipProbability = 0.0;
    int delayBadMinMs = 0;
    int delayBadMaxMs = 0;
};

std::string safeName(const std::string &value)
{
    if (value.empty())
        throw std::invalid_argument("Ten run khong duoc rong");
    for (char c : value)
        if (!std::isalnum(static_cast<unsigned char>(c)) && c != '_' && c != '-')
            throw std::invalid_argument("Ten run chi duoc chua chu, so, _ hoac -");
    return value;
}

bool exists(const std::string &path)
{
    std::ifstream in(path.c_str());
    return in.good();
}

bool ensureDirectory(const std::string &path)
{
    if (CreateDirectoryA(path.c_str(), nullptr) != 0) return true;
    const DWORD attributes = GetFileAttributesA(path.c_str());
    return attributes != INVALID_FILE_ATTRIBUTES &&
           (attributes & FILE_ATTRIBUTE_DIRECTORY) != 0;
}

Options parseOptions(int argc, char **argv)
{
    Options options;
    struct ReverseOverrides
    {
        bool urb = false, dur = false, slot = false, good = false, bad = false, seed = false, burst = false;
        Markov::Config config;
    } reverse;
    options.runId = std::to_string(
        std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()).count());
    for (int i = 1; i < argc; i += 2)
    {
        if (i + 1 >= argc)
            throw std::invalid_argument("Thieu gia tri tham so");
        const std::string key(argv[i]);
        const std::string value(argv[i + 1]);
        if (key == "--run-id") options.runId = safeName(value);
        else if (key == "--scenario") options.scenario = safeName(value);
        else if (key == "--output-dir") options.outputDir = value;
        else
        {
            char *end = nullptr;
            errno = 0;
            const double number = std::strtod(value.c_str(), &end);
            if (errno || end == value.c_str() || *end != '\0' || !std::isfinite(number))
                throw std::invalid_argument("So khong hop le: " + value);
            if (key == "--urb") options.markov.urb = number;
            else if (key == "--dur-s") options.markov.dur_s = number;
            else if (key == "--lossgood") options.markov.lossgood = number;
            else if (key == "--lossbad") options.markov.lossbad = number;
            else if (key == "--flip-probability") options.flipProbability = number;
            else if (key == "--burst-packets") { options.markov.packetMode = true; options.markov.badPackets = number; }
            else if (key == "--reverse-urb") { reverse.config.urb = number; reverse.urb = true; }
            else if (key == "--reverse-dur-s") { reverse.config.dur_s = number; reverse.dur = true; }
            else if (key == "--reverse-lossgood") { reverse.config.lossgood = number; reverse.good = true; }
            else if (key == "--reverse-lossbad") { reverse.config.lossbad = number; reverse.bad = true; }
            else if (key == "--reverse-burst-packets") { reverse.config.packetMode = true; reverse.config.badPackets = number; reverse.burst = true; }
            else if (key == "--seed" || key == "--slot-ms" ||
                     key == "--reverse-seed" || key == "--reverse-slot-ms" ||
                     key == "--sysid" || key == "--listen-port" ||
                     key == "--gateway-source-port" || key == "--gateway-port" ||
                     key == "--measure-seconds" ||
                     key == "--delay-bad-min-ms" || key == "--delay-bad-max-ms")
            {
                const double maximum = (key == "--seed" || key == "--reverse-seed") ? 4294967295.0 :
                                       (key == "--slot-ms" || key == "--reverse-slot-ms") ? 9007199254740991.0 :
                                       key == "--sysid" ? 255.0 :
                                       key == "--measure-seconds" ? 3600.0 :
                                       (key == "--delay-bad-min-ms" || key == "--delay-bad-max-ms") ? 10000.0 : 65535.0;
                if (number < ((key == "--seed" || key == "--reverse-seed" ||
                               key == "--delay-bad-min-ms" || key == "--delay-bad-max-ms") ? 0 : 1) ||
                    number > maximum || number != std::floor(number))
                    throw std::invalid_argument("So nguyen ngoai mien: " + value);
                if (key == "--seed") options.markov.seed = static_cast<std::uint32_t>(number);
                else if (key == "--reverse-seed") { reverse.config.seed = static_cast<std::uint32_t>(number); reverse.seed = true; }
                else if (key == "--slot-ms") options.markov.slot_ms = static_cast<std::uint64_t>(number);
                else if (key == "--reverse-slot-ms") { reverse.config.slot_ms = static_cast<std::uint64_t>(number); reverse.slot = true; }
                else if (key == "--sysid") options.sysid = static_cast<int>(number);
                else if (key == "--listen-port") options.px4ListenPort = static_cast<unsigned short>(number);
                else if (key == "--gateway-port") options.gatewayPort = static_cast<unsigned short>(number);
                else if (key == "--measure-seconds") { options.measureSeconds = static_cast<int>(number); options.measure = true; }
                else if (key == "--delay-bad-min-ms") options.delayBadMinMs = static_cast<int>(number);
                else if (key == "--delay-bad-max-ms") options.delayBadMaxMs = static_cast<int>(number);
                else options.gatewaySourcePort = static_cast<unsigned short>(number);
            }
            else throw std::invalid_argument("Tham so khong biet: " + key);
        }
    }
    if (options.px4ListenPort == options.gatewaySourcePort ||
        options.px4ListenPort == options.gatewayPort ||
        options.gatewaySourcePort == options.gatewayPort)
        throw std::invalid_argument("Cong proxy trung nhau hoac trung Gateway");
    options.markov.validate();
    options.reverseMarkov = options.markov;
    options.reverseMarkov.seed ^= 0x9e3779b9u;
    if (reverse.urb) options.reverseMarkov.urb = reverse.config.urb;
    if (reverse.dur) options.reverseMarkov.dur_s = reverse.config.dur_s;
    if (reverse.slot) options.reverseMarkov.slot_ms = reverse.config.slot_ms;
    if (reverse.good) options.reverseMarkov.lossgood = reverse.config.lossgood;
    if (reverse.bad) options.reverseMarkov.lossbad = reverse.config.lossbad;
    if (reverse.seed) options.reverseMarkov.seed = reverse.config.seed;
    if (reverse.burst) { options.reverseMarkov.packetMode = true; options.reverseMarkov.badPackets = reverse.config.badPackets; }
    options.reverseMarkov.validate();
    if (options.flipProbability < 0.0 || options.flipProbability > 1.0)
        throw std::invalid_argument("flip-probability phai trong [0,1]");
    if (options.delayBadMinMs > options.delayBadMaxMs)
        throw std::invalid_argument("delay-bad-min-ms lon hon max");
    return options;
}

class Proxy
{
public:
    explicit Proxy(const Options &options) : options_(options),
        faultRng_(options.markov.seed ^ 0x464C4950u),
        delayRng_(options.markov.seed ^ 0x44454C41u) {}
    ~Proxy()
    {
        Network::closeSocket(px4Socket_);
        Network::closeSocket(gatewaySocket_);
    }

    int run()
    {
        px4Socket_ = Network::createBoundSocket(SOCK_DGRAM, options_.px4ListenPort);
        gatewaySocket_ = Network::createBoundSocket(SOCK_DGRAM, options_.gatewaySourcePort);
        if (px4Socket_ == INVALID_SOCKET || gatewaySocket_ == INVALID_SOCKET)
            return 1;

        gatewayAddress_.sin_family = AF_INET;
        gatewayAddress_.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        gatewayAddress_.sin_port = htons(options_.gatewayPort);

        if (options_.measure)
        {
        outputDir_ = options_.outputDir.empty()
                         ? "docs/ketqua/PBL3-19_GatewayMarkov/upstream/" + options_.runId
                         : options_.outputDir;
        prefix_ = outputDir_ + "/" + options_.scenario + "_" + options_.runId;
        if (!ensureDirectory("docs") || !ensureDirectory("docs/ketqua") ||
            (options_.outputDir.empty() &&
             (!ensureDirectory("docs/ketqua/PBL3-19_GatewayMarkov") ||
              !ensureDirectory("docs/ketqua/PBL3-19_GatewayMarkov/upstream"))) ||
            !ensureDirectory(outputDir_))
        {
            std::cerr << "Khong tao duoc thu muc ket qua proxy\n";
            return 1;
        }
        if (exists(prefix_ + "_config.txt") ||
            exists(prefix_ + "_states.csv") ||
            exists(prefix_ + "_reverse_states.csv") ||
            exists(prefix_ + "_summary.csv") ||
            exists(prefix_ + "_faults.csv") ||
            exists(prefix_ + "_delay.csv") ||
            exists(prefix_ + "_decision_trace.csv") ||
            exists(prefix_ + "_reverse_trace.csv") ||
            exists(prefix_ + "_post_trace.csv") ||
            exists(prefix_ + "_proxy_pre.csv") ||
            exists(prefix_ + "_proxy_post.csv"))
        {
            std::cerr << "run_id da co file; dung run_id moi\n";
            return 1;
        }
        stateFile_.open((prefix_ + "_states.csv").c_str());
        if (!stateFile_) return 1;
        stateFile_ << "run_id,sysid,t_ms,event,state\n";
        reverseStateFile_.open((prefix_ + "_reverse_states.csv").c_str());
        if (!reverseStateFile_) return 1;
        reverseStateFile_ << "run_id,sysid,t_ms,event,state\n";
        reverseTraceFile_.open((prefix_ + "_reverse_trace.csv").c_str());
        if (!reverseTraceFile_) return 1;
        reverseTraceFile_ << "epoch_ms,run_id,sysid,bytes,msgid,command,state,decision\n";
        postTraceFile_.open((prefix_ + "_post_trace.csv").c_str());
        if (!postTraceFile_) return 1;
        postTraceFile_ << "epoch_ms,sysid,compid,seq,msgid,len,checksum,magic,bit_flipped\n";
        faultFile_.open((prefix_ + "_faults.csv").c_str());
        if (!faultFile_) return 1;
        faultFile_ << "t_s,sysid,compid,seq,msgid,bit_flipped,sent\n";
        delayFile_.open((prefix_ + "_delay.csv").c_str());
        if (!delayFile_) return 1;
        delayFile_ << "t_pre_ms,t_sent_ms,delay_set_ms,delay_observed_ms,seq,msgid\n";
        decisionFile_.open((prefix_ + "_decision_trace.csv").c_str());
        if (!decisionFile_) return 1;
        decisionFile_ << "epoch_ms,t_ms,in_window,sysid,compid,seq,msgid,state,decision\n";
        {
            std::ofstream config((prefix_ + "_config.txt").c_str());
            if (!config) return 1;
            config << "scenario=" << options_.scenario
                   << "\nrun_id=" << options_.runId
                   << "\nsysid=" << options_.sysid
                   << "\npx4_listen_port=" << options_.px4ListenPort
                   << "\ngateway_source_port=" << options_.gatewaySourcePort
                   << "\ngateway_address=127.0.0.1:" << options_.gatewayPort
                   << "\nurb=" << options_.markov.urb
                   << "\ndur_s=" << options_.markov.dur_s
                   << "\nslot_ms=" << options_.markov.slot_ms
                   << "\nmarkov_unit=" << (options_.markov.packetMode ? "frame" : "time")
                   << "\nburst_packets=" << options_.markov.badPackets
                   << "\nlossgood=" << options_.markov.lossgood
                   << "\nlossbad=" << options_.markov.lossbad
                   << "\nseed=" << options_.markov.seed
                   << "\nflip_probability=" << options_.flipProbability
                   << "\ndelay_bad_min_ms=" << options_.delayBadMinMs
                   << "\ndelay_bad_max_ms=" << options_.delayBadMaxMs
                   << "\nreverse_urb=" << options_.reverseMarkov.urb
                   << "\nreverse_dur_s=" << options_.reverseMarkov.dur_s
                   << "\nreverse_slot_ms=" << options_.reverseMarkov.slot_ms
                   << "\nreverse_markov_unit=" << (options_.reverseMarkov.packetMode ? "frame" : "time")
                   << "\nreverse_burst_packets=" << options_.reverseMarkov.badPackets
                   << "\nreverse_lossgood=" << options_.reverseMarkov.lossgood
                   << "\nreverse_lossbad=" << options_.reverseMarkov.lossbad
                   << "\nreverse_seed=" << options_.reverseMarkov.seed
                   << "\nwarmup_s=5\nmeasure_s=" << options_.measureSeconds << '\n';
        }
        if (!preQos_.open("proxy_pre", 3.0, options_.scenario, options_.runId, outputDir_, options_.measureSeconds) ||
            !postQos_.open("proxy_post", 3.0, options_.scenario, options_.runId, outputDir_, options_.measureSeconds))
            return 1;
        }

        std::cout << "UPSTREAM PROXY: PX4 -> Windows UDP " << options_.px4ListenPort
                  << " -> Markov -> Gateway 127.0.0.1:" << options_.gatewayPort
                  << " from 127.0.0.1:" << options_.gatewaySourcePort
                  << " | sysid=" << options_.sysid
                  << " urb=" << options_.markov.urb
                  << " dur_s=" << options_.markov.dur_s
                  << " slot_ms=" << options_.markov.slot_ms
                  << " seed=" << options_.markov.seed << '\n';
        std::cout << "REVERSE MARKOV: Gateway -> PX4"
                  << " urb=" << options_.reverseMarkov.urb
                  << " dur_s=" << options_.reverseMarkov.dur_s
                  << " slot_ms=" << options_.reverseMarkov.slot_ms
                  << " seed=" << options_.reverseMarkov.seed << '\n';
        std::cout << "Che do: " << (options_.measure ? "DO QOS" : "CHAY BINH THUONG") << '\n';
        auto lastReport = Clock::now();
        while (true)
        {
            const TimePoint now = Clock::now();
            flushDelayed(now);
            if (channel_)
            {
                const TimePoint tickAt = options_.measure && !summaryWritten_
                    ? std::min(now, measurementEnd_) : now;
                channel_->tick(msSinceStart(tickAt));
                reverseChannel_->tick(msSinceStart(tickAt));
                if (options_.measure)
                {
                    preQos_.tick(now);
                    postQos_.tick(now);
                    if (!summaryWritten_ && preQos_.finished() && pendingUpstream_.empty())
                        finishMeasurement();
                }
            }
            if (elapsedSeconds(now, lastReport) >= 5.0)
            {
                std::cout << "PROXY STATS: pre=" << preFrames_
                          << " kept=" << keptFrames_
                          << " dropped_markov=" << droppedFrames_
                          << " post_sent=" << postFrames_
                          << " send_errors=" << sendErrors_
                          << " reverse_rx=" << reverseRx_
                          << " reverse_dropped=" << reverseDropped_
                          << " reverse_tx=" << reverseTx_
                          << " crc_errors=" << crcErrors_ << '\n';
                lastReport = now;
            }

            fd_set reads;
            FD_ZERO(&reads);
            FD_SET(px4Socket_, &reads);
            FD_SET(gatewaySocket_, &reads);
            timeval timeout{};
            timeout.tv_usec = pendingUpstream_.empty() ? 200000 : 1000;
            const int ready = select(0, &reads, nullptr, nullptr, &timeout);
            if (ready == SOCKET_ERROR)
            {
                std::cerr << "select loi: " << WSAGetLastError() << '\n';
                return 1;
            }
            if (FD_ISSET(px4Socket_, &reads)) receivePx4();
            if (FD_ISSET(gatewaySocket_, &reads)) receiveGateway();
        }
    }

private:
    struct PendingUpstream
    {
        mavlink_message_t message{};
        std::string frame;
        sockaddr_in sender{};
        TimePoint receivedAt{};
        TimePoint due{};
        bool inWindow = false;
        bool flipped = false;
        int delaySetMs = 0;
    };

    void sendUpstream(const PendingUpstream &item, TimePoint now)
    {
        const int sent = sendto(gatewaySocket_, item.frame.data(),
            static_cast<int>(item.frame.size()), 0,
            reinterpret_cast<const sockaddr *>(&gatewayAddress_),
            sizeof(gatewayAddress_));
        if (sent != static_cast<int>(item.frame.size()))
        {
            if (item.inWindow) ++sendErrors_;
            std::cerr << "sendto Gateway loi: " << WSAGetLastError() << '\n';
            return;
        }
        if (!item.flipped)
            postQos_.onFrame(item.message, item.frame.size(), item.sender, now);
        if (item.flipped && item.inWindow) ++flippedSent_;
        if (item.inWindow) ++postFrames_;
        if (item.delaySetMs > 0 && item.inWindow)
        {
            ++delayedFrames_;
            delayFile_ << msSinceStart(item.receivedAt) << ',' << msSinceStart(now)
                       << ',' << item.delaySetMs << ','
                       << 1000.0 * elapsedSeconds(now, item.receivedAt) << ','
                       << static_cast<int>(item.message.seq) << ','
                       << item.message.msgid << '\n';
        }
        if (item.flipped)
            faultFile_ << elapsedSeconds(item.receivedAt, firstFrame_) << ','
                       << static_cast<int>(item.message.sysid) << ','
                       << static_cast<int>(item.message.compid) << ','
                       << static_cast<int>(item.message.seq) << ','
                       << item.message.msgid << ",1,1\n";
        const auto epochMs = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()).count();
        postTraceFile_ << epochMs << ','
                       << static_cast<unsigned int>(item.message.sysid) << ','
                       << static_cast<unsigned int>(item.message.compid) << ','
                       << static_cast<unsigned int>(item.message.seq) << ','
                       << item.message.msgid << ','
                       << static_cast<unsigned int>(item.message.len) << ','
                       << item.message.checksum << ','
                       << static_cast<unsigned int>(item.message.magic) << ','
                       << (item.flipped ? 1 : 0) << '\n';
    }

    void flushDelayed(TimePoint now)
    {
        for (auto item = pendingUpstream_.begin(); item != pendingUpstream_.end(); )
        {
            if (item->due <= now)
            {
                sendUpstream(*item, now);
                item = pendingUpstream_.erase(item);
            }
            else ++item;
        }
    }

    std::uint64_t msSinceStart(TimePoint now) const
    {
        return static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::milliseconds>(now - firstFrame_).count());
    }

    void receivePx4()
    {
        char bytes[65536];
        sockaddr_in sender{};
        int senderLength = sizeof(sender);
        const int n = recvfrom(px4Socket_, bytes, sizeof(bytes), 0,
            reinterpret_cast<sockaddr *>(&sender), &senderLength);
        if (n == SOCKET_ERROR)
        {
            if (WSAGetLastError() != WSAEWOULDBLOCK)
                std::cerr << "recvfrom PX4 loi: " << WSAGetLastError() << '\n';
            return;
        }
        if (sourceKnown_ && !Network::sameAddress(sender, px4Address_))
        {
            ++foreignDatagrams_;
            return;
        }
        for (int i = 0; i < n; ++i)
        {
            const uint8_t status = parser_.feed(static_cast<std::uint8_t>(bytes[i]));
            if (status == MAVLINK_FRAMING_BAD_CRC) { ++crcErrors_; continue; }
            if (status == MAVLINK_FRAMING_BAD_SIGNATURE) { ++signatureErrors_; continue; }
            if (status != MAVLINK_FRAMING_OK) continue;
            const mavlink_message_t &message = parser_.message;
            if (message.sysid != options_.sysid) { ++foreignFrames_; continue; }
            const TimePoint now = Clock::now();
            if (!sourceKnown_)
            {
                px4Address_ = sender;
                sourceKnown_ = true;
                std::cout << "PX4 SOURCE: " << inet_ntoa(sender.sin_addr)
                          << ':' << ntohs(sender.sin_port) << '\n';
            }
            if (!channel_)
            {
                firstFrame_ = now;
                if (options_.measure)
                {
                    measurementEnd_ = now + std::chrono::seconds(5 + options_.measureSeconds);
                    const TimePoint measurementStart = now + std::chrono::seconds(5);
                    preQos_.setSharedWindow(measurementStart);
                    postQos_.setSharedWindow(measurementStart);
                }
                channel_.reset(new Markov::Channel(options_.markov, options_.sysid, 0,
                    [this](std::uint64_t at, bool bad)
                    {
                        if (options_.measure && !summaryWritten_)
                        {
                            stateFile_ << options_.runId << ',' << options_.sysid
                                       << ',' << at << ','
                                       << (at == 0 ? "INITIAL" : "TRANSITION")
                                       << ',' << (bad ? 'B' : 'G') << '\n';
                            stateFile_.flush();
                        }
                    }));
                reverseChannel_.reset(new Markov::Channel(options_.reverseMarkov,
                    options_.sysid, 0,
                    [this](std::uint64_t at, bool bad)
                    {
                        if (options_.measure && !summaryWritten_)
                        {
                            reverseStateFile_ << options_.runId << ',' << options_.sysid
                                              << ',' << at << ','
                                              << (at == 0 ? "INITIAL" : "TRANSITION")
                                              << ',' << (bad ? 'B' : 'G') << '\n';
                            reverseStateFile_.flush();
                        }
                    }));
                if (options_.measure)
                    std::cout << "PROXY WINDOW: warmup_s=5 measure_s=" << options_.measureSeconds << " run_id="
                              << options_.runId << '\n';
            }
            if (options_.measure && !summaryWritten_ && now >= measurementEnd_ && pendingUpstream_.empty())
            {
                preQos_.tick(now);
                postQos_.tick(now);
                finishMeasurement();
            }

            std::string frame = serialize(message);
            if (frame.empty()) { ++serializeErrors_; continue; }
            preQos_.onFrame(message, frame.size(), sender, now);
            const bool inWindow = !options_.measure || preQos_.inMeasurementWindow(now);
            const bool keep = channel_->keepFrame(msSinceStart(now));
            const bool bad = channel_->isBad();
            const auto decisionEpochMs = std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::system_clock::now().time_since_epoch()).count();
            decisionFile_ << decisionEpochMs << ',' << msSinceStart(now) << ','
                          << (inWindow ? 1 : 0)
                          << ',' << static_cast<int>(message.sysid)
                          << ',' << static_cast<int>(message.compid)
                          << ',' << static_cast<int>(message.seq)
                          << ',' << message.msgid << ','
                          << (bad ? 'B' : 'G') << ','
                          << (keep ? "KEEP" : "DROP") << '\n';
            if (inWindow)
            {
                ++preFrames_;
                if (bad) ++preBadFrames_;
                else ++preGoodFrames_;
            }
            if (!keep)
            {
                if (inWindow)
                {
                    ++droppedFrames_;
                    if (bad) ++droppedBadFrames_;
                    else ++droppedGoodFrames_;
                }
                continue;
            }
            if (inWindow) ++keptFrames_;
            const double random = static_cast<double>(faultRng_()) / 4294967296.0;
            const bool flipped = options_.flipProbability > 0.0 &&
                                 message.len > 0 && random < options_.flipProbability;
            if (flipped)
            {
                const std::size_t payloadOffset = message.magic == MAVLINK_STX_MAVLINK1 ? 6u : 10u;
                if (payloadOffset < frame.size())
                    frame[payloadOffset] = static_cast<char>(
                        static_cast<unsigned char>(frame[payloadOffset]) ^
                        static_cast<unsigned char>(1u << (faultRng_() % 8u)));
                if (inWindow) ++flippedAttempted_;
            }
            PendingUpstream outgoing;
            outgoing.message = message;
            outgoing.frame = std::move(frame);
            outgoing.sender = sender;
            outgoing.receivedAt = now;
            outgoing.inWindow = inWindow;
            outgoing.flipped = flipped;
            if (bad && options_.delayBadMaxMs > 0)
            {
                const unsigned int span = static_cast<unsigned int>(
                    options_.delayBadMaxMs - options_.delayBadMinMs + 1);
                outgoing.delaySetMs = options_.delayBadMinMs +
                    static_cast<int>(delayRng_() % span);
                outgoing.due = now + std::chrono::milliseconds(outgoing.delaySetMs);
                pendingUpstream_.push_back(std::move(outgoing));
            }
            else
                sendUpstream(outgoing, now);
        }
    }

    void receiveGateway()
    {
        char bytes[65536];
        sockaddr_in sender{};
        int senderLength = sizeof(sender);
        const int n = recvfrom(gatewaySocket_, bytes, sizeof(bytes), 0,
            reinterpret_cast<sockaddr *>(&sender), &senderLength);
        if (n == SOCKET_ERROR)
        {
            if (WSAGetLastError() != WSAEWOULDBLOCK)
                std::cerr << "recvfrom Gateway loi: " << WSAGetLastError() << '\n';
            return;
        }
        if (!Network::sameAddress(sender, gatewayAddress_))
        {
            ++foreignDatagrams_;
            return;
        }
        ++reverseRx_;
        if (!sourceKnown_)
        {
            std::cerr << "REVERSE BLOCK: PX4 source chua hoc\n";
            return;
        }
        const TimePoint now = Clock::now();
        const bool inWindow = !options_.measure ||
            (!summaryWritten_ && preQos_.inMeasurementWindow(now));
        const bool keep = reverseChannel_->keepFrame(msSinceStart(now));
        const bool bad = reverseChannel_->isBad();
        int msgid = -1;
        int command = -1;
        MavlinkParser reverseParser;
        for (int i = 0; i < n; ++i)
        {
            if (reverseParser.feed(static_cast<std::uint8_t>(bytes[i])) != MAVLINK_FRAMING_OK)
                continue;
            msgid = static_cast<int>(reverseParser.message.msgid);
            if (reverseParser.message.msgid == MAVLINK_MSG_ID_COMMAND_LONG)
            {
                mavlink_command_long_t decoded{};
                mavlink_msg_command_long_decode(&reverseParser.message, &decoded);
                command = decoded.command;
            }
            break;
        }
        const auto epochMs = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()).count();
        reverseTraceFile_ << epochMs << ',' << options_.runId << ','
                          << options_.sysid << ',' << n << ','
                          << msgid << ',' << command << ','
                          << (bad ? 'B' : 'G') << ','
                          << (keep ? "KEEP" : "DROP") << '\n';
        reverseTraceFile_.flush();
        if (inWindow) ++reverseMeasuredRx_;
        if (!keep)
        {
            ++reverseDropped_;
            if (inWindow) ++reverseMeasuredDropped_;
            return;
        }
        const int sent = sendto(px4Socket_, bytes, n, 0,
            reinterpret_cast<const sockaddr *>(&px4Address_), sizeof(px4Address_));
        if (sent == n)
        {
            ++reverseTx_;
            if (inWindow) ++reverseMeasuredTx_;
            std::cout << "REVERSE: Gateway -> PX4 "
                      << inet_ntoa(px4Address_.sin_addr) << ':'
                      << ntohs(px4Address_.sin_port)
                      << " bytes=" << sent << '\n';
        }
        else
        {
            if (inWindow) ++reverseMeasuredSendErrors_;
            std::cerr << "sendto PX4 loi: " << WSAGetLastError() << '\n';
        }
    }

    void finishMeasurement()
    {
        summaryWritten_ = true;
        decisionFile_.flush();
        postTraceFile_.flush();
        faultFile_.flush();
        delayFile_.flush();
        reverseTraceFile_.flush();
        channel_->tick(msSinceStart(measurementEnd_));
        reverseChannel_->tick(msSinceStart(measurementEnd_));
        stateFile_ << options_.runId << ',' << options_.sysid << ','
                   << msSinceStart(measurementEnd_) << ",END,"
                   << (channel_->isBad() ? 'B' : 'G') << '\n';
        stateFile_.flush();
        reverseStateFile_ << options_.runId << ',' << options_.sysid << ','
                          << msSinceStart(measurementEnd_) << ",END,"
                          << (reverseChannel_->isBad() ? 'B' : 'G') << '\n';
        reverseStateFile_.flush();
        const Markov::Stats &s = channel_->stats();
        const Markov::Stats &reverse = reverseChannel_->stats();
        std::ofstream out((prefix_ + "_summary.csv").c_str());
        out << "run_id,sysid,frames_pre,frames_pre_good,frames_pre_bad,"
               "frames_dropped_good,frames_dropped_bad,frames_kept,frames_dropped_markov,"
               "frames_post_sent,send_errors,pre_qos_frames,post_qos_frames,"
               "slots_including_warmup,bad_slots_including_warmup,"
               "bad_fraction_including_warmup,complete_bad_runs,mean_bad_s,"
               "crc_errors,signature_errors,foreign_frames,foreign_datagrams,"
               "serialize_errors,reverse_rx,reverse_tx,reverse_dropped_total,"
               "reverse_frames_pre,reverse_frames_dropped_markov,reverse_frames_post_sent,"
               "reverse_send_errors,reverse_bad_fraction_including_warmup,"
               "reverse_complete_bad_runs,reverse_mean_bad_s,"
               "flipped_attempted,flipped_sent,delayed_frames\n";
        out << options_.runId << ',' << options_.sysid << ','
            << preFrames_ << ',' << preGoodFrames_ << ',' << preBadFrames_ << ','
            << droppedGoodFrames_ << ',' << droppedBadFrames_ << ','
            << keptFrames_ << ',' << droppedFrames_ << ','
            << postFrames_ << ',' << sendErrors_ << ','
            << preQos_.totalFrames(options_.sysid) << ','
            << postQos_.totalFrames(options_.sysid) << ','
            << s.slots << ',' << s.badSlots << ',' << s.badFraction() << ','
            << s.completeBadRuns << ',' << s.meanBadSeconds() << ','
            << crcErrors_ << ',' << signatureErrors_ << ','
            << foreignFrames_ << ',' << foreignDatagrams_ << ','
            << serializeErrors_ << ',' << reverseRx_ << ',' << reverseTx_ << ','
            << reverseDropped_ << ',' << reverseMeasuredRx_ << ','
            << reverseMeasuredDropped_ << ',' << reverseMeasuredTx_ << ','
            << reverseMeasuredSendErrors_ << ',' << reverse.badFraction() << ','
            << reverse.completeBadRuns << ',' << reverse.meanBadSeconds() << ','
            << flippedAttempted_ << ',' << flippedSent_ << ',' << delayedFrames_ << '\n';
        out.close();
        if (preFrames_ != preGoodFrames_ + preBadFrames_ ||
            droppedFrames_ != droppedGoodFrames_ + droppedBadFrames_ ||
            preFrames_ != keptFrames_ + droppedFrames_ ||
            keptFrames_ != postFrames_ + sendErrors_ ||
            preFrames_ != preQos_.totalFrames(options_.sysid) ||
            (options_.delayBadMaxMs == 0 &&
             postFrames_ != postQos_.totalFrames(options_.sysid) + flippedSent_) ||
            reverseMeasuredRx_ != reverseMeasuredDropped_ +
                reverseMeasuredTx_ + reverseMeasuredSendErrors_)
            std::cerr << "PROXY QOS DOI SOAT LOI\n";
        std::cout << "UPSTREAM RESULT: pre=" << preFrames_
                  << " pre_good=" << preGoodFrames_
                  << " pre_bad=" << preBadFrames_
                  << " kept=" << keptFrames_
                  << " dropped_markov=" << droppedFrames_
                  << " dropped_good=" << droppedGoodFrames_
                  << " dropped_bad=" << droppedBadFrames_
                  << " post_sent=" << postFrames_
                  << " send_errors=" << sendErrors_
                  << " reverse_pre=" << reverseMeasuredRx_
                  << " reverse_dropped=" << reverseMeasuredDropped_
                  << " reverse_post=" << reverseMeasuredTx_
                  << " slots_including_warmup=" << s.slots
                  << " summary=" << prefix_ << "_summary.csv\n";
    }

    Options options_;
    SOCKET px4Socket_ = INVALID_SOCKET;
    SOCKET gatewaySocket_ = INVALID_SOCKET;
    sockaddr_in gatewayAddress_{};
    sockaddr_in px4Address_{};
    bool sourceKnown_ = false;
    MavlinkParser parser_;
    QosRecorder preQos_;
    QosRecorder postQos_;
    std::unique_ptr<Markov::Channel> channel_;
    std::unique_ptr<Markov::Channel> reverseChannel_;
    TimePoint firstFrame_{};
    TimePoint measurementEnd_{};
    std::string outputDir_;
    std::string prefix_;
    std::ofstream stateFile_;
    std::ofstream reverseStateFile_;
    std::ofstream reverseTraceFile_;
    std::ofstream postTraceFile_;
    std::ofstream faultFile_;
    std::ofstream delayFile_;
    std::ofstream decisionFile_;
    std::mt19937 faultRng_;
    std::mt19937 delayRng_;
    std::deque<PendingUpstream> pendingUpstream_;
    bool summaryWritten_ = false;
    std::uint64_t preFrames_ = 0;
    std::uint64_t preGoodFrames_ = 0;
    std::uint64_t preBadFrames_ = 0;
    std::uint64_t keptFrames_ = 0;
    std::uint64_t droppedFrames_ = 0;
    std::uint64_t droppedGoodFrames_ = 0;
    std::uint64_t droppedBadFrames_ = 0;
    std::uint64_t postFrames_ = 0;
    std::uint64_t sendErrors_ = 0;
    std::uint64_t flippedAttempted_ = 0;
    std::uint64_t flippedSent_ = 0;
    std::uint64_t delayedFrames_ = 0;
    std::uint64_t reverseRx_ = 0;
    std::uint64_t reverseTx_ = 0;
    std::uint64_t reverseDropped_ = 0;
    std::uint64_t reverseMeasuredRx_ = 0;
    std::uint64_t reverseMeasuredDropped_ = 0;
    std::uint64_t reverseMeasuredTx_ = 0;
    std::uint64_t reverseMeasuredSendErrors_ = 0;
    std::uint64_t crcErrors_ = 0;
    std::uint64_t signatureErrors_ = 0;
    std::uint64_t foreignFrames_ = 0;
    std::uint64_t foreignDatagrams_ = 0;
    std::uint64_t serializeErrors_ = 0;
};
}

int main(int argc, char **argv)
{
    std::cout << std::unitbuf;
    std::cerr << std::unitbuf;
    Options options;
    try { options = parseOptions(argc, argv); }
    catch (const std::exception &error)
    {
        std::cerr << error.what() << "\nUsage: upstream_markov_proxy.exe "
                  << "[--run-id ID] [--scenario NAME] [--output-dir DIR] [--sysid 1..255] "
                  << "[--listen-port N] [--gateway-source-port N] [--gateway-port N] "
                  << "[--urb N] [--dur-s N] [--slot-ms N] "
                  << "[--lossgood N] [--lossbad N] [--seed N] "
                  << "[--reverse-urb N] [--reverse-dur-s N] [--reverse-slot-ms N] "
                  << "[--reverse-lossgood N] [--reverse-lossbad N] [--reverse-seed N]\n";
        return 1;
    }
    Network::Runtime winsock;
    if (winsock.error() != 0)
    {
        std::cerr << "WSAStartup loi: " << winsock.error() << '\n';
        return 1;
    }
    Proxy proxy(options);
    return proxy.run();
}
