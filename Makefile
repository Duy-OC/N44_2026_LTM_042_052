CXX = g++
CXXFLAGS = -std=c++11 -O2 -Isrc/common -Isrc/gateway -Isrc/proxy -Isrc/client -Ithird_party
LDFLAGS = -lws2_32

BIN_DIR = bin
TARGETS = $(BIN_DIR)/gateway.exe $(BIN_DIR)/tcpclient.exe $(BIN_DIR)/upstream_markov_proxy.exe $(BIN_DIR)/t0_2_udp_listener.exe

all: $(BIN_DIR) $(TARGETS)

$(BIN_DIR):
	mkdir $(BIN_DIR)

$(BIN_DIR)/gateway.exe: src/gateway/gateway.cpp
	$(CXX) $(CXXFLAGS) -o $@ $< $(LDFLAGS)

$(BIN_DIR)/tcpclient.exe: src/client/tcpclient.cpp
	$(CXX) $(CXXFLAGS) -o $@ $< $(LDFLAGS)

$(BIN_DIR)/upstream_markov_proxy.exe: src/proxy/upstream_markov_proxy.cpp
	$(CXX) $(CXXFLAGS) -o $@ $< $(LDFLAGS)

$(BIN_DIR)/t0_2_udp_listener.exe: tests/t0_2_udp_listener.cpp
	$(CXX) $(CXXFLAGS) -o $@ $< $(LDFLAGS)

clean:
	rm -rf $(BIN_DIR) *.exe docs/ketqua/*
