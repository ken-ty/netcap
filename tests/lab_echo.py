"""Echo traffic for the pass-through lab in test_e2e.py (docs/design.md: Destinations that pass through).

  python3 lab_echo.py serve              TCP echo on port 5201 and UDP echo on port 53, IPv4 and IPv6
  python3 lab_echo.py tcp <address>      send 250 kB and read it back; print the seconds it took
  python3 lab_echo.py udp53 <address>    150 datagrams of 1200 bytes, one at a time; print the seconds

At 1 Mbit/s each way, tcp takes about 2.5 seconds and udp53 about 1.5 (measured on a runner: 60 datagrams took 0.58).
Without a cap both take milliseconds.
"""
import socket
import sys
import threading
import time

TCP_PORT, DNS_PORT = 5201, 53
TCP_BYTES, UDP_COUNT, UDP_SIZE = 250_000, 150, 1200


def serve():
    def tcp_echo(conn):
        with conn:
            while data := conn.recv(65536):
                conn.sendall(data)

    tcp = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    tcp.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp.bind(("::", TCP_PORT))
    tcp.listen()
    udp = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    udp.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    udp.bind(("::", DNS_PORT))

    def udp_echo():
        while True:
            data, peer = udp.recvfrom(65536)
            udp.sendto(data, peer)

    threading.Thread(target=udp_echo, daemon=True).start()
    print("ready", flush=True)
    while True:
        conn, _ = tcp.accept()
        threading.Thread(target=tcp_echo, args=(conn,), daemon=True).start()


def tcp(addr):
    start = time.monotonic()
    with socket.create_connection((addr, TCP_PORT), timeout=30) as s:
        sender = threading.Thread(target=s.sendall, args=(b"x" * TCP_BYTES,))
        sender.start()
        got = 0
        while got < TCP_BYTES:
            got += len(s.recv(65536))
        sender.join()
    return time.monotonic() - start


def udp53(addr):
    family = socket.AF_INET6 if ":" in addr else socket.AF_INET
    start = time.monotonic()
    with socket.socket(family, socket.SOCK_DGRAM) as s:
        s.settimeout(5)
        for _ in range(UDP_COUNT):
            s.sendto(b"x" * UDP_SIZE, (addr, DNS_PORT))
            s.recvfrom(65536)
    return time.monotonic() - start


if __name__ == "__main__":
    if sys.argv[1] == "serve":
        serve()
    else:
        print(f"{ {'tcp': tcp, 'udp53': udp53}[sys.argv[1]](sys.argv[2]):.3f}")
