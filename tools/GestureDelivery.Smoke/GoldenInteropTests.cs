using System;
using System.IO;
using System.Text.Json;
using Google.Protobuf;
using NUnit.Framework;
using Suzukaze.Gesture.Protocol;
using Suzukaze.Gesture.Delivery.Tests;

public class GoldenInteropTests
{
    [Test]
    public void AllPythonFixturesMatchConstructedCSharpMessagesAndRoundTrip()
    {
        using var document = JsonDocument.Parse(File.ReadAllText(Path.Combine(TestContext.CurrentContext.TestDirectory, "messages.json")));
        foreach (var fixture in document.RootElement.EnumerateArray())
        {
            var dict = fixture.GetProperty("message");
            var expected = new GestureEnvelope {
                Version = dict.GetProperty("version").GetUInt32(),
                SessionId = dict.GetProperty("session_id").GetString()
            };
            switch (dict.GetProperty("type").GetString())
            {
                case "state":
                    var state = new State {
                        Sequence = dict.GetProperty("sequence").GetUInt64(),
                        SentAt = dict.GetProperty("sent_at").GetDouble(),
                        StaleTimeout = dict.GetProperty("stale_timeout").GetDouble(),
                        Fresh = dict.GetProperty("fresh").GetBoolean(),
                        Tracking = dict.GetProperty("tracking").GetBoolean(),
                        Gesture = dict.GetProperty("gesture").GetString() switch {
                            "NONE" => ContinuousGesture.None,
                            "FANNING" => ContinuousGesture.Fanning,
                            "RELAXING" => ContinuousGesture.Relaxing,
                            _ => throw new Exception("Unknown fixture gesture")
                        }
                    };
                    if (dict.GetProperty("observed_at").ValueKind != JsonValueKind.Null)
                        state.ObservedAt = dict.GetProperty("observed_at").GetDouble();
                    if (dict.GetProperty("frame_id").ValueKind != JsonValueKind.Null)
                        state.FrameId = dict.GetProperty("frame_id").GetUInt64();
                    if (dict.GetProperty("source_timestamp").ValueKind != JsonValueKind.Null)
                        state.SourceTimestamp = dict.GetProperty("source_timestamp").GetDouble();
                    expected.State = state;
                    break;
                case "event":
                    expected.Event = new Event {
                        EventId = dict.GetProperty("event_id").GetUInt64(),
                        Gesture = dict.GetProperty("gesture").GetString() == "RAMUNE" ? OccurrenceGesture.Ramune : OccurrenceGesture.Uchimizu,
                        OccurredAt = dict.GetProperty("occurred_at").GetDouble(),
                        ExpiresAt = dict.GetProperty("expires_at").GetDouble()
                    };
                    break;
                case "ack":
                    expected.Ack = new Ack {
                        EventId = dict.GetProperty("event_id").GetUInt64(),
                        Status = (AckStatus)Enum.Parse(typeof(AckStatus), dict.GetProperty("status").GetString(), true)
                    };
                    break;
            }
            var bytes = WireTests.Hex(fixture.GetProperty("protobuf_hex").GetString());
            Assert.That(expected.ToByteArray(), Is.EqualTo(bytes));
            Assert.That(GestureEnvelope.Parser.ParseFrom(bytes), Is.EqualTo(expected));
        }
    }
}
