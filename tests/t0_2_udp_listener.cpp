// ============================================================================
// Test T0.2: UDP Listener - Kiem thu nhan luong UDP MAVLink tu PX4
// ============================================================================
#include "network.h"
#include "config.h"
#include "time_utils.h"

#include <iostream>
#include <iomanip>
#include <cstdlib>

int main(int argc, char **argv)
{
    std::cout << std::unitbuf;
    std::cerr << std::unitbuf;

    unsigned short port = Config::UDP_PORT; // 14550
    if (argc >= 2)
    {
        port = static_cast<unsigned short>(std::atoi(argv[1]));
    }

    Network::Runtime winsock;
    if (winsock.error() != 0)
    {
        std::cerr << "[T0.2 ERROR] WSAStartup that bai: " << winsock.error() << "\n";
        return 1;
    }

    SOCKET udpSocket = Network::createBoundSocket(SOCK_DGRAM, port);
    if (udpSocket == INVALID_SOCKET)
    {
        std::cerr << "[T0.2 ERROR] Khong the tao va bind socket UDP tren cong " << port << "\n";
        return 1;
    }

    std::cout << "========================================================\n"
              << "  [TEST T0.2] Chuong trinh lang nghe UDP tu PX4 SITL    \n"
              << "  Lang nghe tai: 0.0.0.0:" << port << "\n"
              << "  Tieu chi dat: Nhan lien tuc cac byte du lieu tu PX4   \n"
              << "  Nhan Ctrl+C de dung                                   \n"
              << "========================================================\n\n";

    char buffer[65536];
    sockaddr_in sender{};
    int senderLen = sizeof(sender);

    unsigned long long totalDatagrams = 0;
    unsigned long long totalBytes = 0;
    unsigned long long periodDatagrams = 0;
    unsigned long long periodBytes = 0;

    TimePoint lastReport = Clock::now();
    TimePoint startTime = lastReport;

    while (true)
    {
        fd_set reads;
        FD_ZERO(&reads);
        FD_SET(udpSocket, &reads);

        timeval timeout{};
        timeout.tv_sec = 0;
        timeout.tv_usec = 100000; // 100ms

        int ready = select(0, &reads, nullptr, nullptr, &timeout);
        if (ready == SOCKET_ERROR)
        {
            std::cerr << "[T0.2 ERROR] select() loi: " << WSAGetLastError() << "\n";
            break;
        }

        if (FD_ISSET(udpSocket, &reads))
        {
            int received = recvfrom(
                udpSocket,
                buffer,
                sizeof(buffer),
                0,
                reinterpret_cast<sockaddr *>(&sender),
                &senderLen);

            if (received > 0)
            {
                totalDatagrams++;
                totalBytes += received;
                periodDatagrams++;
                periodBytes += received;

                // Kiem tra ky tu magic MAVLink v1 (0xFE) hoac v2 (0xFD)
                uint8_t magic = static_cast<uint8_t>(buffer[0]);
                const char *ver = (magic == 0xFD) ? "MAVLink v2" :
                                  (magic == 0xFE) ? "MAVLink v1" : "Raw UDP";

                if (totalDatagrams <= 5 || totalDatagrams % 50 == 0)
                {
                    std::cout << "[T0.2 RX #" << totalDatagrams << "] "
                              << inet_ntoa(sender.sin_addr) << ":" << ntohs(sender.sin_port)
                              << " -> " << received << " bytes (" << ver << ")\n";
                }
            }
        }

        TimePoint now = Clock::now();
        double elapsed = elapsedSeconds(now, lastReport);
        if (elapsed >= 1.0)
        {
            double pps = periodDatagrams / elapsed;
            double kbps = (periodBytes * 8.0 / 1000.0) / elapsed;

            std::cout << "--- [T0.2 STATUS] Thoi gian: "
                      << std::fixed << std::setprecision(1) << elapsedSeconds(now, startTime) << "s"
                      << " | Toc do: " << std::setprecision(1) << pps << " pkts/s ("
                      << kbps << " kbps)"
                      << " | Tong nhan: " << totalDatagrams << " pkts ("
                      << totalBytes << " bytes) ---\n";

            periodDatagrams = 0;
            periodBytes = 0;
            lastReport = now;
        }
    }

    Network::closeSocket(udpSocket);
    return 0;
}
