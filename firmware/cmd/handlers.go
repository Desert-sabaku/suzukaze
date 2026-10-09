package main

import (
	micon_v1 "firmware/gen/micon/v1"
)

var (
	CommitHash = "dev" // makeで挿入
	SchemaHash = "dev"
)

// handleHandshake は HandshakeReq を受け取ったら自分の VersionInfo を積んだ
// HandshakeResp を返す。Matched はスキーマハッシュのみで判定する
// (コミットハッシュはビルドごとに変わるため一致確認には使わない)。
func handleHandshake(pt *PacketTransceiver, req *micon_v1.HandshakeReq) {
	resp := &micon_v1.Packet{
		Payload: &micon_v1.Packet_HandshakeResp{
			HandshakeResp: &micon_v1.HandshakeResp{
				ControllerVersion: &micon_v1.VersionInfo{
					SchemaHash: SchemaHash,
					CommitHash: CommitHash,
				},
				UptimeMs: UptimeMs(),
				Matched:  req.GetClientVersion().GetSchemaHash() == SchemaHash,
			},
		},
	}
	_ = pt.SendPacket(resp)
}
