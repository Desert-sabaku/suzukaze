from multiprocessing import freeze_support


def run_gesture_detection() -> None:
    from gesture_detection.modules.app import main as run_application

    run_application()


def run_unity_bridge() -> None:
    from unity_bridge.unity_bridge import main as run_bridge

    run_bridge()


def main() -> None:
    mode = (
        input(
            "Choose mode (1: gesture detection, 2: unity bridge): "
        )
        .strip()
        .lower()
    )

    if mode in {"1", "gesture", "gesture_detection"}:
        freeze_support()
        run_gesture_detection()
    elif mode in {"2", "unity", "unity_bridge"}:
        run_unity_bridge()
    else:
        print("Invalid input.")


if __name__ == "__main__":
    freeze_support()
    main()
