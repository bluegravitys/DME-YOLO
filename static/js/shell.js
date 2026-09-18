(function () {
    const waitForDesktopApi = (callback) => {
        if (window.pywebview && window.pywebview.api) {
            callback(window.pywebview.api);
            return;
        }

        const readyHandler = () => {
            if (window.pywebview && window.pywebview.api) {
                callback(window.pywebview.api);
            }
        };

        window.addEventListener("pywebviewready", readyHandler, { once: true });

        let attempts = 0;
        const timer = window.setInterval(() => {
            attempts += 1;
            if (window.pywebview && window.pywebview.api) {
                window.clearInterval(timer);
                callback(window.pywebview.api);
            } else if (attempts > 40) {
                window.clearInterval(timer);
            }
        }, 250);
    };

    const installDesktopScrollBridge = () => {
        const pageShell = document.querySelector(".page-shell");
        if (!pageShell) {
            return;
        }

        const isEditable = (target) => {
            return Boolean(target.closest("input, textarea, select, [contenteditable='true']"));
        };

        document.addEventListener(
            "wheel",
            (event) => {
                if (!document.body.classList.contains("is-desktop-client")) {
                    return;
                }

                if (isEditable(event.target)) {
                    return;
                }

                const canScroll = pageShell.scrollHeight > pageShell.clientHeight;
                if (!canScroll) {
                    return;
                }

                const delta = event.deltaY;
                if (delta === 0) {
                    return;
                }

                pageShell.scrollTop += delta;
                event.preventDefault();
            },
            { passive: false }
        );
    };

    const syncMaximizeButton = (button, isMaximized) => {
        if (!button) {
            return;
        }

        button.classList.toggle("is-active", Boolean(isMaximized));
        button.setAttribute("aria-label", isMaximized ? "还原窗口" : "最大化");
        button.setAttribute("title", isMaximized ? "还原窗口" : "最大化");
    };

    waitForDesktopApi((api) => {
        const controlsRoot = document.querySelector("[data-window-controls]");
        if (!controlsRoot) {
            return;
        }

        document.body.classList.add("is-desktop-client");
        controlsRoot.hidden = false;
        installDesktopScrollBridge();

        const maximizeButton = controlsRoot.querySelector('[data-window-action="maximize"]');
        const dragRegion = document.querySelector(".app-chrome-drag");
        let isActionPending = false;
        syncMaximizeButton(maximizeButton, false);

        controlsRoot.addEventListener("click", async (event) => {
            const button = event.target.closest("[data-window-action]");
            if (!button || isActionPending) {
                return;
            }

            try {
                isActionPending = true;
                const action = button.dataset.windowAction;
                if (action === "minimize") {
                    await api.minimize();
                } else if (action === "maximize") {
                    const isMaximized = await api.toggle_maximize();
                    syncMaximizeButton(maximizeButton, isMaximized);
                } else if (action === "close") {
                    await api.close();
                }
            } catch (error) {
                console.error("Window action failed:", error);
            } finally {
                window.setTimeout(() => {
                    isActionPending = false;
                }, 160);
            }
        });

        if (dragRegion) {
            dragRegion.addEventListener("dblclick", async () => {
                if (isActionPending) {
                    return;
                }

                try {
                    isActionPending = true;
                    const isMaximized = await api.toggle_maximize();
                    syncMaximizeButton(maximizeButton, isMaximized);
                } catch (error) {
                    console.error("Maximize toggle failed:", error);
                } finally {
                    window.setTimeout(() => {
                        isActionPending = false;
                    }, 160);
                }
            });
        }
    });
})();