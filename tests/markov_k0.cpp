#include "emulator.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>

struct Result
{
    std::uint64_t dropped = 0;
    std::uint64_t bursts = 0;
    std::uint64_t longest = 0;
    std::uint64_t hash = 1469598103934665603ULL;
    double mean = 0.0;
};

static Result run(double loss, double burstMean, std::uint32_t seed)
{
    Markov::Config config;
    config.urb = loss;
    config.packetMode = true;
    config.badPackets = burstMean;
    config.lossgood = 0.0;
    config.lossbad = 1.0;
    config.seed = seed;
    Markov::Channel channel(config, 1, 0);
    Result result;
    std::uint64_t current = 0;
    for (std::uint64_t packet = 0; packet < 100000; ++packet)
    {
        const bool kept = channel.keepFrame(packet);
        result.hash = (result.hash ^ static_cast<unsigned>(kept)) * 1099511628211ULL;
        if (!kept)
        {
            ++result.dropped;
            ++current;
        }
        else if (current)
        {
            ++result.bursts;
            result.longest = std::max(result.longest, current);
            current = 0;
        }
    }
    if (current)
    {
        ++result.bursts;
        result.longest = std::max(result.longest, current);
    }
    result.mean = result.bursts ? static_cast<double>(result.dropped) / result.bursts : 0.0;
    return result;
}

int main(int argc, char **argv)
{
    if (argc != 2)
    {
        std::cerr << "Usage: markov_k0.exe output.csv\n";
        return 2;
    }
    std::ofstream out(argv[1]);
    if (!out)
        return 2;
    out << "case,repeat,seed,packets,loss_target_pct,burst_target_packets,p_gb,p_bg,"
           "dropped,loss_actual_pct,bursts,burst_mean_packets,burst_max_packets,"
           "seed_reproducible\n";
    const double losses[] = {0.0, 0.05, 0.05, 0.10};
    const double lengths[] = {4.0, 4.0, 1.0, 4.0};
    const char *names[] = {"K1", "K2", "K3", "K4"};
    for (int scenario = 0; scenario < 4; ++scenario)
    {
        for (int repeat = 1; repeat <= 3; ++repeat)
        {
            const std::uint32_t seed = 1000u * scenario + repeat;
            const Result value = run(losses[scenario], lengths[scenario], seed);
            const Result again = run(losses[scenario], lengths[scenario], seed);
            const double r = 1.0 / lengths[scenario];
            const double p = r * losses[scenario] / (1.0 - losses[scenario]);
            const bool reproducible = value.hash == again.hash &&
                                      value.dropped == again.dropped;
            out << names[scenario] << ',' << repeat << ',' << seed
                << ",100000," << losses[scenario] * 100.0 << ',' << lengths[scenario]
                << ',' << p << ',' << r << ',' << value.dropped
                << ',' << static_cast<double>(value.dropped) / 1000.0
                << ',' << value.bursts << ',' << value.mean
                << ',' << value.longest << ',' << (reproducible ? "PASS" : "FAIL") << '\n';
            if (!reproducible)
                return 1;
        }
    }
    std::cout << "K0: 12 synthetic runs, 100000 packets each, 3 seeds per scenario\n";
    return 0;
}
