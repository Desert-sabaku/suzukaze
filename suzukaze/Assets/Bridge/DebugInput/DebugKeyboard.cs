#if UNITY_STANDALONE_WIN || UNITY_EDITOR_WIN
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Threading;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.LowLevel;

namespace Suzukaze.DebugInput
{
    // デバッグ用キーボード(ewin)の入力を、ウィンドウにフォーカスがなくても読む。
    // Windows の Raw Input(RIDEV_INPUTSINK)で全キー入力を受け、デバイスのパスが
    // DeviceId を含むものだけを仮想キーボードに流す。既存の Keyboard.current を読むコードはそのまま動く。
    //
    // DeviceId は環境変数 DEBUG_KEYBOARD_ID でも上書きできる(例: VID_1234&PID_5678)。
    // 空のあいだは何も流さず、キーを押したデバイスのパスをログに出すので、そこから VID/PID を調べる。
    public sealed class DebugKeyboard : MonoBehaviour
    {
        private const string DeviceId = "VID_05AC&PID_0257";
        private const string EnvName = "DEBUG_KEYBOARD_ID";

        private struct KeyEvent
        {
            public int VKey;
            public bool Extended;
            public bool Down;
        }

        private readonly ConcurrentQueue<KeyEvent> events = new();
        private readonly ConcurrentQueue<string> logs = new();
        private Thread thread;
        private volatile bool running;
        private volatile uint threadId;
        private string filter;
        private Keyboard device;
        private KeyboardState state;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void Create()
        {
            if (FindAnyObjectByType<DebugKeyboard>()) return;
            var host = new GameObject("DebugKeyboard");
            host.AddComponent<DebugKeyboard>();
            DontDestroyOnLoad(host);
        }

        private void OnEnable()
        {
            filter = Environment.GetEnvironmentVariable(EnvName);
            if (string.IsNullOrWhiteSpace(filter)) filter = DeviceId;
            filter = filter.Trim();

#if UNITY_EDITOR
            // エディターは既定で Game ビューにフォーカスがないと入力を捨てる。
            InputSystem.settings.editorInputBehaviorInPlayMode =
                InputSettings.EditorInputBehaviorInPlayMode.AllDeviceInputAlwaysGoesToGameView;
#endif
            if (filter.Length > 0)
                device = InputSystem.AddDevice<Keyboard>("DebugKeyboard");
            else
                Debug.LogWarning($"DebugKeyboard: {EnvName} が空です。キーを押したデバイスのパスをログに出します。");

            running = true;
            thread = new Thread(MessageLoop) { IsBackground = true, Name = "DebugKeyboard" };
            thread.Start();
        }

        private void OnDisable()
        {
            running = false;
            if (threadId != 0) PostThreadMessage(threadId, WM_QUIT, IntPtr.Zero, IntPtr.Zero);
            thread?.Join(500);
            thread = null;
            if (device != null && device.added) InputSystem.RemoveDevice(device);
            device = null;
            state = default;
        }

        private void Update()
        {
            while (logs.TryDequeue(out var log)) Debug.Log(log);
            while (events.TryDequeue(out var e))
            {
                if (device == null || !device.added) continue;
                var key = ToKey(e.VKey, e.Extended);
                if (key == Key.None) continue;
                state.Set(key, e.Down);
                InputSystem.QueueStateEvent(device, state);
            }
        }

        private void MessageLoop()
        {
            threadId = GetCurrentThreadId();
            // 親を HWND_MESSAGE(-3) にした見えないウィンドウ。WM_INPUT を受け取るためだけに使う。
            var hwnd = CreateWindowEx(0, "STATIC", "DebugKeyboard", 0, 0, 0, 0, 0,
                new IntPtr(-3), IntPtr.Zero, IntPtr.Zero, IntPtr.Zero);
            if (hwnd == IntPtr.Zero)
            {
                logs.Enqueue("DebugKeyboard: ウィンドウを作れませんでした");
                return;
            }

            var rid = new RAWINPUTDEVICE { UsagePage = 1, Usage = 6, Flags = RIDEV_INPUTSINK, Target = hwnd };
            if (!RegisterRawInputDevices(new[] { rid }, 1, (uint)Marshal.SizeOf<RAWINPUTDEVICE>()))
            {
                logs.Enqueue("DebugKeyboard: Raw Input の登録に失敗しました");
                DestroyWindow(hwnd);
                return;
            }

            var names = new Dictionary<IntPtr, string>();
            var logged = new HashSet<string>();
            while (running && GetMessage(out var msg, IntPtr.Zero, 0, 0) > 0)
            {
                if (msg.Message != WM_INPUT) continue; // ディスパッチしない。WM_INPUT だけを読む。
                if (!ReadKeyboard(msg.LParam, out var hDevice, out var key)) continue;

                if (!names.TryGetValue(hDevice, out var name))
                    names[hDevice] = name = GetDeviceName(hDevice);

                if (filter.Length == 0)
                {
                    if (logged.Add(name)) logs.Enqueue($"DebugKeyboard: キー入力のあるデバイス {name}");
                    continue;
                }
                if (name.IndexOf(filter, StringComparison.OrdinalIgnoreCase) < 0) continue;
                events.Enqueue(key);
            }

            var remove = new RAWINPUTDEVICE { UsagePage = 1, Usage = 6, Flags = RIDEV_REMOVE, Target = IntPtr.Zero };
            RegisterRawInputDevices(new[] { remove }, 1, (uint)Marshal.SizeOf<RAWINPUTDEVICE>());
            DestroyWindow(hwnd);
        }

        private static bool ReadKeyboard(IntPtr lParam, out IntPtr device, out KeyEvent key)
        {
            device = IntPtr.Zero;
            key = default;
            var headerSize = (uint)Marshal.SizeOf<RAWINPUTHEADER>();
            uint size = 0;
            GetRawInputData(lParam, RID_INPUT, IntPtr.Zero, ref size, headerSize);
            if (size == 0) return false;

            var buffer = Marshal.AllocHGlobal((int)size);
            try
            {
                if (GetRawInputData(lParam, RID_INPUT, buffer, ref size, headerSize) != size) return false;
                var header = Marshal.PtrToStructure<RAWINPUTHEADER>(buffer);
                if (header.Type != RIM_TYPEKEYBOARD) return false;
                var keyboard = Marshal.PtrToStructure<RAWKEYBOARD>(buffer + (int)headerSize);
                device = header.Device;
                key = new KeyEvent
                {
                    VKey = keyboard.VKey,
                    Extended = (keyboard.Flags & RI_KEY_E0) != 0,
                    Down = (keyboard.Flags & RI_KEY_BREAK) == 0,
                };
                return true;
            }
            finally
            {
                Marshal.FreeHGlobal(buffer);
            }
        }

        private static string GetDeviceName(IntPtr device)
        {
            uint size = 0;
            GetRawInputDeviceInfo(device, RIDI_DEVICENAME, IntPtr.Zero, ref size);
            if (size == 0) return "";
            var buffer = Marshal.AllocHGlobal((int)size * 2);
            try
            {
                GetRawInputDeviceInfo(device, RIDI_DEVICENAME, buffer, ref size);
                return Marshal.PtrToStringUni(buffer) ?? "";
            }
            finally
            {
                Marshal.FreeHGlobal(buffer);
            }
        }

        // 仮想キーコードから Input System の Key へ。このプロジェクトで使うキーと一般的なキーだけ。
        private static Key ToKey(int vkey, bool extended)
        {
            if (vkey >= 0x41 && vkey <= 0x5A) return Key.A + (vkey - 0x41);
            if (vkey == 0x30) return Key.Digit0;
            if (vkey >= 0x31 && vkey <= 0x39) return Key.Digit1 + (vkey - 0x31);
            if (vkey >= 0x60 && vkey <= 0x69) return Key.Numpad0 + (vkey - 0x60);
            if (vkey >= 0x70 && vkey <= 0x7B) return Key.F1 + (vkey - 0x70);
            return vkey switch
            {
                0x0D => extended ? Key.NumpadEnter : Key.Enter,
                0x1B => Key.Escape,
                0x20 => Key.Space,
                0x09 => Key.Tab,
                0x08 => Key.Backspace,
                0x25 => Key.LeftArrow,
                0x26 => Key.UpArrow,
                0x27 => Key.RightArrow,
                0x28 => Key.DownArrow,
                0x10 => Key.LeftShift,
                0x11 => Key.LeftCtrl,
                0x12 => Key.LeftAlt,
                _ => Key.None,
            };
        }

        private const uint WM_INPUT = 0x00FF;
        private const uint WM_QUIT = 0x0012;
        private const uint RID_INPUT = 0x10000003;
        private const uint RIDI_DEVICENAME = 0x20000007;
        private const uint RIDEV_REMOVE = 0x00000001;
        private const uint RIDEV_INPUTSINK = 0x00000100;
        private const uint RIM_TYPEKEYBOARD = 1;
        private const ushort RI_KEY_BREAK = 1;
        private const ushort RI_KEY_E0 = 2;

        [StructLayout(LayoutKind.Sequential)]
        private struct RAWINPUTDEVICE
        {
            public ushort UsagePage;
            public ushort Usage;
            public uint Flags;
            public IntPtr Target;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct RAWINPUTHEADER
        {
            public uint Type;
            public uint Size;
            public IntPtr Device;
            public IntPtr WParam;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct RAWKEYBOARD
        {
            public ushort MakeCode;
            public ushort Flags;
            public ushort Reserved;
            public ushort VKey;
            public uint Message;
            public uint ExtraInformation;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct MSG
        {
            public IntPtr Hwnd;
            public uint Message;
            public IntPtr WParam;
            public IntPtr LParam;
            public uint Time;
            public int X;
            public int Y;
        }

        [DllImport("user32.dll", SetLastError = true)]
        private static extern bool RegisterRawInputDevices(
            [In] RAWINPUTDEVICE[] devices, uint count, uint size);

        [DllImport("user32.dll")]
        private static extern uint GetRawInputData(
            IntPtr rawInput, uint command, IntPtr data, ref uint size, uint headerSize);

        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        private static extern uint GetRawInputDeviceInfo(
            IntPtr device, uint command, IntPtr data, ref uint size);

        [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern IntPtr CreateWindowEx(
            uint exStyle, string className, string windowName, uint style,
            int x, int y, int width, int height,
            IntPtr parent, IntPtr menu, IntPtr instance, IntPtr param);

        [DllImport("user32.dll")]
        private static extern bool DestroyWindow(IntPtr hwnd);

        [DllImport("user32.dll")]
        private static extern int GetMessage(out MSG msg, IntPtr hwnd, uint min, uint max);

        [DllImport("user32.dll")]
        private static extern bool PostThreadMessage(uint threadId, uint msg, IntPtr wParam, IntPtr lParam);

        [DllImport("kernel32.dll")]
        private static extern uint GetCurrentThreadId();
    }
}
#endif
