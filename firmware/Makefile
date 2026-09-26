TARGET ?= pico

# 現在のコミットハッシュ(未コミット変更があれば -dirty を付与)
GIT_COMMIT := $(shell git describe --always --dirty)

# proto/以下の全.protoファイルからハッシュを計算(先頭8文字)
SCHEMA_HASH := $(shell cat ../proto/comms/v1/*.proto | sha256sum | cut -c1-8)

# TinyGoに埋め込むフラグ
LDFLAGS := -X main.GitCommit=$(GIT_COMMIT) -X main.SchemaHash=$(SCHEMA_HASH)

all: build

build:
	@echo "=== Building firmware (Commit: $(GIT_COMMIT), Schema: $(SCHEMA_HASH)) ==="
	tinygo build -target=$(TARGET) -ldflags="$(LDFLAGS)" -o firmware.uf2 ./cmd

flash:
	@echo "=== Flashing to $(TARGET) ==="
	tinygo flash -target=$(TARGET) -ldflags="$(LDFLAGS)" ./cmd

clean:
	@echo "=== Cleaning binary ==="
	rm -f firmware.uf2

.PHONY: all build flash clean
