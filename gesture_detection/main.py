from multiprocessing import freeze_support


def main():
    from modules.app import main as run_application

    run_application()


if __name__ == "__main__":
    freeze_support()
    main()
