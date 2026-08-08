"""Static intervention recommendation library (DWS spec).

5 categories × 3 levels × 12 recommendations = 180 items.
Also contains trigger priority order and static reason lines.
"""

# ---------------------------------------------------------------------------
# Trigger priority order (highest → lowest)
# ---------------------------------------------------------------------------
TRIGGER_PRIORITY: list[str] = [
    "recovery",
    "workload",
    "physical_activity",
    "nutrition",
    "engagement",
]

# ---------------------------------------------------------------------------
# Static reason lines per category (appended / used as AI fallback)
# ---------------------------------------------------------------------------
REASON_LINES: dict[str, str] = {
    "recovery": (
        "Your sleep and energy have been low for several days, "
        "reducing recovery and performance."
    ),
    "workload": (
        "Your stress and workload are elevated, increasing strain "
        "and reducing effectiveness."
    ),
    "physical_activity": (
        "Your stress is high while movement is low, "
        "limiting recovery and stress regulation."
    ),
    "nutrition": (
        "Low energy and high stress suggest your nutrition may be "
        "limiting performance."
    ),
    "engagement": (
        "Your engagement has been low, reducing focus and "
        "meaningful output."
    ),
}

# ---------------------------------------------------------------------------
# Fallback recommendations (no active trigger)
# ---------------------------------------------------------------------------
FALLBACK_RECOMMENDATIONS: list[str] = [
    "Complete your check-in today.",
    "Prioritize sleep, food, and hydration.",
    "Reduce strain where possible today.",
]

# ---------------------------------------------------------------------------
# Main library: category → level (1-3) → list[str]
# ---------------------------------------------------------------------------
INTERVENTION_LIBRARY: dict[str, dict[int, list[str]]] = {
    "recovery": {
        1: [
            "Go to bed 1 hour earlier tonight.",
            "Begin a 20-minute wind-down routine tonight.",
            "Avoid caffeine after 2 PM today.",
            "Protect a consistent sleep window tonight.",
            "Reduce screen time before bed tonight.",
            "Drink water consistently throughout the day.",
            "Dim lights 30 minutes before bed tonight.",
            "Stop late-night scrolling tonight.",
            "Set a bedtime reminder for tonight.",
            "Keep your bedtime consistent tonight.",
            "Avoid heavy meals late tonight.",
            "Slow your evening pace during the last hour before bed.",
        ],
        2: [
            "Start a 30-minute wind-down routine tonight.",
            "Do not use screens during the 30 minutes before bed.",
            "Be in bed by a fixed time tonight.",
            "Stop stimulating activities 1 hour before bed.",
            "Keep your phone away from your bed tonight.",
            "Avoid work during the last hour of the day.",
            "Create a quiet sleep environment tonight.",
            "Reduce bright light exposure tonight.",
            "Shut down all non-essential activity after dinner.",
            "Use a simple pre-sleep routine tonight.",
            "Avoid caffeine for the rest of today.",
            "Prioritize recovery over late-night productivity tonight.",
        ],
        3: [
            "Stop all work 1 hour before bed tonight.",
            "Remove your phone from the room before bed tonight.",
            "Follow a strict bedtime tonight.",
            "Eliminate all non-essential evening tasks tonight.",
            "Protect recovery as your top priority tonight.",
            "Shut down devices 1 hour before bed tonight.",
            "Reset your sleep environment before going to bed tonight.",
            "Use a full recovery routine tonight.",
            "Do not do any work after your evening shutdown time.",
            "Go to bed at the same time tonight with no exceptions.",
            "Remove all evening distractions before bed tonight.",
            "Prioritize sleep over unfinished tasks tonight.",
        ],
    },
    "workload": {
        1: [
            "Write down your top 3 priorities for today.",
            "Remove one non-essential task from your list today.",
            "Block 60 minutes for focused work today.",
            "Work on one task at a time until it is complete.",
            "Sort your tasks by importance before starting.",
            "Set a clear stop time for today.",
            "Complete your highest-priority task first.",
            "Delay one low-value task until later.",
            "Reduce unnecessary multitasking today.",
            "Spend the next work block on one defined priority.",
            "Review your task list and simplify it.",
            "Finish one important task before starting another.",
        ],
        2: [
            "Remove two low-priority tasks from your list today.",
            "Delegate one task today if possible.",
            "Set a hard stop time for work today.",
            "Restructure your day around your top priorities.",
            "Eliminate avoidable distractions during your next focus block.",
            "Batch similar tasks together today.",
            "Focus only on high-impact work during your next work block.",
            "Reduce meeting time where possible today.",
            "Protect one uninterrupted block for deep work today.",
            "Pause non-essential tasks until tomorrow.",
            "Narrow your attention to what must get done today.",
            "Reduce task switching for the rest of today.",
        ],
        3: [
            "Complete only essential tasks today.",
            "Reset your full schedule around your highest priorities.",
            "Notify others of your limits today if needed.",
            "Remove current commitments that are not essential.",
            "Enforce a hard boundary on work today.",
            "Reduce the scope of today's workload.",
            "Protect deep work and decline unnecessary interruptions.",
            "End work at your set stop time today.",
            "Strip your list down to critical tasks only.",
            "Postpone all low-value work today.",
            "Work only on what directly matters most today.",
            "Shut down work once essential tasks are complete.",
        ],
    },
    "physical_activity": {
        1: [
            "Take a 10-minute walk today.",
            "Stretch for 5 to 10 minutes today.",
            "Move for 5 to 10 minutes after your next task.",
            "Break up long sitting periods today.",
            "Stand up and move at least once every hour today.",
            "Add one short movement break to your day.",
            "Walk during one of your breaks today.",
            "Do light activity instead of staying seated during your next break.",
            "Take the stairs or choose the longer walking route today.",
            "Get outside for a short walk today.",
            "Do a short mobility routine today.",
            "Move your body before the day ends.",
        ],
        2: [
            "Complete 20 minutes of activity today.",
            "Take movement breaks throughout the day.",
            "Split activity into two short sessions today.",
            "Do a structured mobility routine today.",
            "Schedule movement into your day and complete it.",
            "Increase your activity intensity slightly today.",
            "Block time for exercise today.",
            "Take a brisk walk today.",
            "Complete one intentional exercise session today.",
            "Move before or after work today.",
            "Add a second short walk to your day.",
            "Prioritize movement instead of another sitting period today.",
        ],
        3: [
            "Complete a 30-minute exercise session today.",
            "Move before starting work today.",
            "Block time for training and protect it today.",
            "Complete a structured workout today.",
            "Treat physical activity as a priority today.",
            "Do a higher-effort training session today.",
            "Finish your workout before the evening if possible.",
            "Protect a dedicated movement block today.",
            "Commit to a full exercise session today.",
            "Do not skip planned movement today.",
            "Complete training before moving to non-essential tasks.",
            "Use exercise to reset your stress today.",
        ],
    },
    "nutrition": {
        1: [
            "Eat at least 2 structured meals today.",
            "Drink water consistently today.",
            "Replace one processed snack with a real meal today.",
            "Add protein to your next meal.",
            "Avoid skipping meals today.",
            "Eat a real meal instead of grazing today.",
            "Start the day with a balanced meal.",
            "Choose water instead of a sugary drink today.",
            "Build your next meal around protein and real food today.",
            "Reduce mindless snacking today.",
            "Eat before energy drops too low today.",
            "Keep nutrition simple and consistent today.",
        ],
        2: [
            "Eat 3 structured meals today.",
            "Include protein in each meal today.",
            "Avoid sugary drinks today.",
            "Keep your meal timing consistent today.",
            "Increase whole foods today.",
            "Reduce processed food today.",
            "Drink water with each meal today.",
            "Eat meals at regular times today.",
            "Build balanced meals instead of snack-based eating today.",
            "Avoid skipping lunch or dinner today.",
            "Use real meals to stabilize your energy today.",
            "Keep food choices structured for the rest of today.",
        ],
        3: [
            "Plan your meals for the day.",
            "Avoid processed snacks today.",
            "Follow consistent meal timing today.",
            "Use a full-day nutrition structure today.",
            "Prioritize real meals over convenience foods today.",
            "Eliminate sugary drinks for the rest of today.",
            "Build every meal around protein and real food today.",
            "Do not replace meals with snacks today.",
            "Keep nutrition disciplined and predictable today.",
            "Eat on schedule today.",
            "Prepare your next meal before hunger gets high.",
            "Treat food as fuel for performance today.",
        ],
    },
    "engagement": {
        1: [
            "Complete one meaningful task today.",
            "Reach out to one person today.",
            "Reflect on your main goal for today.",
            "Spend 10 minutes on a high-impact task.",
            "Identify your most important task today.",
            "Start with one task that matters.",
            "Reconnect to the reason today matters.",
            "Finish one task that moves you forward.",
            "Do one thing today that creates progress.",
            "Focus on one meaningful outcome today.",
            "Spend the next work block on something that matters.",
            "Move one priority forward today.",
        ],
        2: [
            "Spend 15 minutes on high-impact work today.",
            "Connect with someone who can support your progress today.",
            "Align your next task with your main goal today.",
            "Remove one low-value task and replace it with meaningful work.",
            "Increase connection instead of working in isolation today.",
            "Complete one focused block on something important today.",
            "Recenter your attention on purposeful work today.",
            "Choose progress over busyness today.",
            "Work on something aligned with your longer-term goals today.",
            "Reduce distraction and do one meaningful thing well today.",
            "Re-engage with a priority you have been avoiding.",
            "Give your best energy to one important task today.",
        ],
        3: [
            "Remove low-value work from today's schedule.",
            "Reconnect your work to a larger purpose today.",
            "Protect time for deep, meaningful work today.",
            "Reset your direction before continuing your day.",
            "Prioritize purpose over busyness today.",
            "Eliminate distractions and work with intention today.",
            "Spend focused time on what matters most today.",
            "Strip away low-value activity and recommit to meaningful work.",
            "Choose long-term progress over short-term noise today.",
            "Protect your attention for important work today.",
            "Rebuild today around one important outcome.",
            "Recommit to work that actually matters today.",
        ],
    },
}
