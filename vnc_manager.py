"""
VNC Server Manager for Remote Browser Viewing

Manages Xvfb (virtual display) and x11vnc server to enable
remote viewing of Selenium browser sessions.
"""

import os
import subprocess
import time
import logging
import signal
import atexit

logger = logging.getLogger(__name__)

class VNCManager:
    """Manages VNC server for remote browser viewing."""

    def __init__(self, display=":99", vnc_port=5900, websocket_port=6080, resolution="1920x1080x24"):
        self.display = display
        self.vnc_port = vnc_port
        self.websocket_port = websocket_port
        self.resolution = resolution
        self.xvfb_process = None
        self.x11vnc_process = None
        self.websockify_process = None
        self.running = False

        # Register cleanup on exit
        atexit.register(self.stop)

    def start(self):
        """Start Xvfb and x11vnc server."""
        if self.running:
            logger.info("VNC server already running")
            return True

        try:
            # Start Xvfb (virtual display)
            logger.info(f"Starting Xvfb on display {self.display}")
            self.xvfb_process = subprocess.Popen(
                ["Xvfb", self.display, "-screen", "0", self.resolution, "-ac", "+extension", "GLX", "+render", "-noreset"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            # Wait for Xvfb to initialize
            time.sleep(2)

            # Check if Xvfb started successfully
            if self.xvfb_process.poll() is not None:
                logger.error("Xvfb failed to start")
                return False

            logger.info(f"Xvfb started successfully on {self.display}")

            # Start x11vnc
            logger.info(f"Starting x11vnc on port {self.vnc_port}")
            self.x11vnc_process = subprocess.Popen(
                [
                    "x11vnc",
                    "-display", self.display,
                    "-rfbport", str(self.vnc_port),
                    "-shared",
                    "-forever",
                    "-nopw",  # No password for simplicity (could add later)
                    "-quiet"
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            # Wait for x11vnc to initialize
            time.sleep(1)

            # Check if x11vnc started successfully
            if self.x11vnc_process.poll() is not None:
                logger.error("x11vnc failed to start")
                self.stop()
                return False

            logger.info(f"x11vnc started successfully on port {self.vnc_port}")

            # Start websockify for web-based VNC viewing
            logger.info(f"Starting websockify on port {self.websocket_port}")
            try:
                import sys
                self.websockify_process = subprocess.Popen(
                    [
                        sys.executable, "-m", "websockify",
                        "--web", "/dev/null",  # No web files needed, we'll serve our own
                        str(self.websocket_port),
                        f"localhost:{self.vnc_port}"
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )

                time.sleep(1)

                if self.websockify_process.poll() is not None:
                    # Process died, capture error output
                    stdout, stderr = self.websockify_process.communicate(timeout=1)
                    error_msg = stderr.decode('utf-8') if stderr else stdout.decode('utf-8') if stdout else "Unknown error"
                    logger.error(f"websockify failed to start: {error_msg}")
                    self.websockify_process = None
                else:
                    logger.info(f"websockify started successfully on port {self.websocket_port}")
            except FileNotFoundError as e:
                logger.error(f"websockify not found: {e}")
                self.websockify_process = None
            except Exception as e:
                logger.error(f"Failed to start websockify: {e}")
                self.websockify_process = None

            self.running = True

            # Set DISPLAY environment variable for Chrome
            os.environ["DISPLAY"] = self.display

            return True

        except FileNotFoundError as e:
            logger.warning(f"VNC components not found: {e}. VNC viewing will not be available.")
            return False
        except Exception as e:
            logger.error(f"Failed to start VNC server: {e}")
            self.stop()
            return False

    def stop(self):
        """Stop Xvfb and x11vnc server."""
        if not self.running:
            return

        logger.info("Stopping VNC server...")

        # Stop websockify
        if self.websockify_process:
            try:
                self.websockify_process.terminate()
                self.websockify_process.wait(timeout=5)
            except Exception as e:
                logger.warning(f"Error stopping websockify: {e}")
                try:
                    self.websockify_process.kill()
                except:
                    pass

        # Stop x11vnc
        if self.x11vnc_process:
            try:
                self.x11vnc_process.terminate()
                self.x11vnc_process.wait(timeout=5)
            except Exception as e:
                logger.warning(f"Error stopping x11vnc: {e}")
                try:
                    self.x11vnc_process.kill()
                except:
                    pass

        # Stop Xvfb
        if self.xvfb_process:
            try:
                self.xvfb_process.terminate()
                self.xvfb_process.wait(timeout=5)
            except Exception as e:
                logger.warning(f"Error stopping Xvfb: {e}")
                try:
                    self.xvfb_process.kill()
                except:
                    pass

        self.running = False
        logger.info("VNC server stopped")

    def get_display(self):
        """Get the DISPLAY variable for Chrome."""
        return self.display if self.running else None

    def is_running(self):
        """Check if VNC server is running."""
        return self.running


# Global VNC manager instance
_vnc_manager = None


def get_vnc_manager():
    """Get or create the global VNC manager instance."""
    global _vnc_manager
    if _vnc_manager is None:
        _vnc_manager = VNCManager()
    return _vnc_manager


def ensure_vnc_running():
    """Ensure VNC server is running and return the display."""
    manager = get_vnc_manager()
    if not manager.is_running():
        manager.start()
    return manager.get_display()
