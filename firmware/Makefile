TARGET ?= pico

# 現在のコミットハッシュ(未コミット変更があれば -dirty を付与)
COMMIT_HASH := $(shell git describe --always --dirty)

# proto/以下の全.protoファイルからハッシュを計算(先頭8文字)
SCHEMA_HASH := $(shell cat ../proto/micon/v1/*.proto | sha256sum | cut -c1-8)

# TinyGoに埋め込むフラグ
LDFLAGS := -X main.CommitHash=$(COMMIT_HASH) -X main.SchemaHash=$(SCHEMA_HASH)

all: flash

build:
	@echo "=== Building firmware (Commit: $(COMMIT_HASH), Schema: $(SCHEMA_HASH)) ==="
	tinygo build -target=$(TARGET) -ldflags="$(LDFLAGS)" -o firmware.uf2 ./cmd

flash:
	@echo "=== Flashing to $(TARGET) (Commit: $(COMMIT_HASH), Schema: $(SCHEMA_HASH)) ==="
	tinygo flash -target=$(TARGET) -ldflags="$(LDFLAGS)" ./cmd

clean:
	@echo "=== Cleaning binary ==="
	rm -f firmware.uf2

.PHONY: all build flash clean
