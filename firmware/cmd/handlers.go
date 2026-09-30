package main

import (
	comms_v1 "firmware/gen/comms/v1"
)

var (
  GitCommit = "dev" // makeで挿入
  SchemaHash = "dev"
)

// handleHandshake は HandshakeReq を受け取ったら自分の VersionInfo を積んだ
// HandshakeResp を返す。Matched はスキーマハッシュのみで判定する
// (コミットハッシュはビルドごとに変わるため一致確認には使わない)。
func handleHandshake(pt *PacketTransceiver, req *comms_v1.HandshakeReq) {
	resp := &comms_v1.Packet{
		Payload: &comms_v1.Packet_HandshakeResp{
			HandshakeResp: &comms_v1.HandshakeResp{
				ControllerVersion: &comms_v1.VersionInfo{
					SchemaHash: SchemaHash,
					CommitHash: GitCommit,
				},
				UptimeMs: UptimeMs(),
				Matched:  req.GetClientVersion().GetSchemaHash() == SchemaHash,
			},
		},
	}
	_ = pt.SendPacket(resp)
}
