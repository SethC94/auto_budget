def run_ngrok(domain):
    """I need to keep ngrok running on the specified domain, restarting if needed.
    TODO: If I get ERR_NGROK_108, I should alert myself and pause before retrying.
    TODO: If ngrok ever adds an API for agent session management, I should automate that here.
    """
    NGROK_DASHBOARD_URL = "https://dashboard.ngrok.com/agents"
    while True:
        kill_existing_ngrok()
        logger.info("Starting ngrok tunnel...")
        try:
            proc = subprocess.Popen(
                ["ngrok", "http", "--domain", domain, "5000"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            out, err = proc.communicate()
            out_str = out.decode("utf-8", errors="ignore")
            err_str = err.decode("utf-8", errors="ignore")

            if proc.returncode != 0:
                logger.error(f"ngrok failed: {err_str}")

                if "ERR_NGROK_108" in err_str or "Your account is limited to 1 simultaneous ngrok agent sessions" in err_str:
                    msg = (
                        "ngrok failed to start: Too many sessions (ERR_NGROK_108).\n"
                        "I need to clear old agent sessions in the ngrok dashboard before I can connect again.\n"
                        f"Please visit {NGROK_DASHBOARD_URL} and terminate any existing tunnels.\n"
                        "After clearing old sessions, the app will retry automatically."
                    )
                    logger.error(msg)
                    send_error_email(
                        "Budget App ngrok Failure: Too Many Sessions",
                        f"{msg}\n\nFull error:\n{err_str}"
                    )
                    # Optional: Open browser tab if interactive. Uncomment if desired.
                    # import webbrowser
                    # webbrowser.open(NGROK_DASHBOARD_URL)
                    # Wait longer before retrying
                    time.sleep(120)
                else:
                    send_error_email(
                        "Budget App ngrok Failure",
                        f"ngrok failed to start: {err_str}"
                    )
                    time.sleep(10)
            else:
                # ngrok started successfully
                time.sleep(10)
        except Exception as e:
            logger.error(f"ngrok crashed: {e}")
            send_error_email("Budget App ngrok Crash", f"ngrok crashed: {e}")
            time.sleep(10)
