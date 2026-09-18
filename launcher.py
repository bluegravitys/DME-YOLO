from app import find_available_port, run_server


def main() -> None:
    port = find_available_port(host="127.0.0.1", start_port=7860)
    run_server(host="127.0.0.1", port=port, open_browser=True)


if __name__ == "__main__":
    main()
