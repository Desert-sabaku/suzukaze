# 現在のコミットハッシュ
GIT_COMMIT := $(shell git describe --always --dirty)

# proto ファイルからハッシュを計算
SCHEMA_HASH := $(shell sha256sum comms.proto | cut -c1-8)
