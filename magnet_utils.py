import time
import math

def ease_out_cubic(t):
    """ A 'Cool' easing function that feels like a physical magnet pull (starts fast, slows down at the end) """
    return 1 - pow(1 - t, 3)

def check_magnet_snap(root, monitor, threshold, on_snap_finished):
    """
    Checks if the window is close to an edge.
    If yes: Animates a 'magnetic pull' to the edge and returns True.
    If no: Returns False.
    """
    x = root.winfo_x()
    y = root.winfo_y()
    w = root.winfo_width()
    h = root.winfo_height()
    
    # Define snap targets
    target_x = x
    target_y = y
    snapped = False
    snap_mode = None # 'top', 'left', 'right'

    # 1. Check distance to LEFT edge
    if abs(x - monitor['l']) < threshold:
        target_x = monitor['l']
        snapped = True
        snap_mode = 'left'
    
    # 2. Check distance to RIGHT edge
    elif abs((x + w) - monitor['r']) < threshold:
        target_x = monitor['r'] - w
        snapped = True
        snap_mode = 'right'

    # 3. Check distance to TOP edge
    # Priority: If we are close to top, we prefer top docking over side docking usually
    if abs(y - monitor['t']) < threshold:
        target_y = monitor['t']
        snapped = True
        snap_mode = 'top'

    if not snapped:
        return False, None

    # --- START ANIMATION ---
    start_x, start_y = x, y
    steps = 15  # Total frames for the animation
    duration_ms = 150 # Total time (fast snap)
    step_time = duration_ms // steps

    def _animate_step(step):
        if step > steps:
            # Animation Done: Ensure exact final position
            root.geometry(f"{w}x{h}+{int(target_x)}+{int(target_y)}")
            if on_snap_finished:
                on_snap_finished(snap_mode)
            return

        # Calculate progress (0.0 to 1.0)
        progress = step / steps
        ease = ease_out_cubic(progress)

        # Interpolate position
        current_x = start_x + (target_x - start_x) * ease
        current_y = start_y + (target_y - start_y) * ease
        
        root.geometry(f"{w}x{h}+{int(current_x)}+{int(current_y)}")
        root.after(step_time, lambda: _animate_step(step + 1))

    # Kick off the animation
    _animate_step(0)
    return True, snap_mode