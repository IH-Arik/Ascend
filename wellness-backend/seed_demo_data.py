import asyncio
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta

sys.path.append(os.getcwd())

from app.core.security import get_password_hash
from app.db.mongodb import get_database, init_db
from app.models.action_log import LeaderActionLog
from app.models.app_setting import AppSetting
from app.models.assessment import Answer, CheckIn, DailyCheckIn, MonthlyCheckIn, WeeklyCheckIn
from app.models.profile import Profile
from app.models.score import DimensionScore, Score
from app.models.user import User


@dataclass(frozen=True)
class DemoMember:
    name: str
    email: str
    company: str
    department: str
    team: str
    role: str
    age: int
    gender: str
    template: str


DEMO_PASSWORD = "Demo@123"
DEMO_PASSWORD_HASH = get_password_hash(DEMO_PASSWORD)

DOMINION_MEMBERS = [
    DemoMember("Ava Morgan", "ava.morgan@demo.dominion.ai", "Dominion Wellness Solutions", "Performance Operations", "OPS Strategy", "Operations Lead", 34, "Female", "stable"),
    DemoMember("Noah Brooks", "noah.brooks@demo.dominion.ai", "Dominion Wellness Solutions", "Performance Operations", "Recovery Programs", "Performance Coach", 31, "Male", "optimal"),
    DemoMember("Mia Patel", "mia.patel@demo.dominion.ai", "Dominion Wellness Solutions", "Product", "AI Product", "Product Manager", 29, "Female", "strained"),
    DemoMember("Ethan Scott", "ethan.scott@demo.dominion.ai", "Dominion Wellness Solutions", "Product", "Platform", "Product Manager", 36, "Male", "high_risk"),
    DemoMember("Sophia Reed", "sophia.reed@demo.dominion.ai", "Dominion Wellness Solutions", "Client Success", "Customer Success", "Support Specialist", 28, "Female", "stable"),
    DemoMember("Lucas Gray", "lucas.gray@demo.dominion.ai", "Dominion Wellness Solutions", "Client Success", "Implementation", "Support Specialist", 33, "Male", "critical"),
    DemoMember("Isla Bennett", "isla.bennett@demo.dominion.ai", "Dominion Wellness Solutions", "Sales", "Business Development", "Sales Executive", 30, "Female", "strained"),
    DemoMember("Mason Clark", "mason.clark@demo.dominion.ai", "Dominion Wellness Solutions", "Sales", "Partnerships", "Sales Executive", 38, "Male", "optimal"),
]

GLOBAL_MEMBERS = [
    DemoMember("Olivia Hart", "olivia.hart@demo.global.ai", "Global Tech Solutions", "Engineering", "Platform", "Engineering Manager", 35, "Female", "stable"),
    DemoMember("Liam Foster", "liam.foster@demo.global.ai", "Global Tech Solutions", "Engineering", "Mobile", "Software Engineer", 27, "Male", "optimal"),
    DemoMember("Emma Diaz", "emma.diaz@demo.global.ai", "Global Tech Solutions", "Product Design", "UX Research", "Product Design", 30, "Female", "stable"),
    DemoMember("James Cole", "james.cole@demo.global.ai", "Global Tech Solutions", "Sales", "Enterprise Sales", "Sales Executive", 32, "Male", "strained"),
]

NORTHSTAR_MEMBERS = [
    DemoMember("Harper Long", "harper.long@demo.northstar.ai", "Northstar Health Group", "Clinical Operations", "Care Delivery", "Clinical Operations Analyst", 34, "Female", "stable"),
    DemoMember("Benjamin Lee", "benjamin.lee@demo.northstar.ai", "Northstar Health Group", "Regional Support", "North Region", "Regional Lead", 40, "Male", "optimal"),
    DemoMember("Ella Turner", "ella.turner@demo.northstar.ai", "Northstar Health Group", "Wellness Programs", "Program Delivery", "Wellness Coordinator", 29, "Female", "strained"),
    DemoMember("Henry Ross", "henry.ross@demo.northstar.ai", "Northstar Health Group", "Account Management", "Strategic Accounts", "Account Manager", 37, "Male", "high_risk"),
]

DEMO_MEMBERS = DOMINION_MEMBERS + GLOBAL_MEMBERS + NORTHSTAR_MEMBERS

PROFILE_PRESETS = {
    "optimal": {
        "overall": [84, 86, 87, 88, 89, 90, 91],
        "dimensions": {"PC": 88, "MR": 85, "MC": 84, "PA": 87, "RC": 89},
        "energy": [80, 82, 83, 84, 82, 85, 86],
        "motivation": [78, 80, 82, 84, 81, 83, 85],
        "recovery": [82, 84, 85, 86, 84, 87, 88],
        "sleep": ["7-8", "7-8", "More than 8", "7-8", "7-8", "More than 8", "7-8"],
        "stress": ["Low", "Low", "About average", "Low", "Low", "About average", "Low"],
        "weekly_workload": [74, 78],
        "weekly_climate": [86, 88],
        "monthly_motivation": [84, 86],
        "monthly_workload": [76, 78],
        "monthly_support": [88, 90],
        "monthly_recognition": [86, 89],
    },
    "stable": {
        "overall": [70, 72, 73, 74, 74, 75, 76],
        "dimensions": {"PC": 72, "MR": 70, "MC": 68, "PA": 74, "RC": 71},
        "energy": [65, 67, 68, 69, 70, 68, 71],
        "motivation": [66, 68, 70, 72, 71, 72, 73],
        "recovery": [62, 64, 65, 66, 66, 67, 68],
        "sleep": ["6-7", "6-7", "7-8", "6-7", "6-7", "7-8", "6-7"],
        "stress": ["About average", "Low", "About average", "About average", "Low", "About average", "Low"],
        "weekly_workload": [60, 64],
        "weekly_climate": [72, 74],
        "monthly_motivation": [70, 72],
        "monthly_workload": [62, 64],
        "monthly_support": [74, 76],
        "monthly_recognition": [72, 75],
    },
    "strained": {
        "overall": [61, 60, 58, 57, 56, 55, 54],
        "dimensions": {"PC": 58, "MR": 52, "MC": 48, "PA": 56, "RC": 50},
        "energy": [48, 47, 46, 45, 44, 43, 42],
        "motivation": [52, 50, 48, 46, 45, 44, 43],
        "recovery": [44, 43, 42, 40, 39, 38, 37],
        "sleep": ["6-7", "4-5", "4-5", "6-7", "4-5", "4-5", "4-5"],
        "stress": ["High", "High", "About average", "High", "High", "High", "Very high"],
        "weekly_workload": [44, 42],
        "weekly_climate": [56, 52],
        "monthly_motivation": [46, 44],
        "monthly_workload": [43, 40],
        "monthly_support": [54, 50],
        "monthly_recognition": [56, 52],
    },
    "high_risk": {
        "overall": [46, 44, 43, 41, 40, 39, 38],
        "dimensions": {"PC": 42, "MR": 38, "MC": 35, "PA": 44, "RC": 34},
        "energy": [34, 33, 32, 31, 30, 29, 28],
        "motivation": [40, 39, 38, 36, 35, 34, 33],
        "recovery": [30, 29, 28, 27, 26, 25, 24],
        "sleep": ["4-5", "Less than 4", "4-5", "4-5", "Less than 4", "4-5", "Less than 4"],
        "stress": ["Very high", "High", "Very high", "Very high", "High", "Very high", "Very high"],
        "weekly_workload": [32, 30],
        "weekly_climate": [44, 40],
        "monthly_motivation": [38, 34],
        "monthly_workload": [30, 28],
        "monthly_support": [42, 38],
        "monthly_recognition": [40, 36],
    },
    "critical": {
        "overall": [30, 28, 27, 25, 24, 22, 20],
        "dimensions": {"PC": 26, "MR": 24, "MC": 18, "PA": 28, "RC": 20},
        "energy": [24, 23, 22, 21, 20, 18, 16],
        "motivation": [28, 26, 24, 22, 20, 18, 16],
        "recovery": [22, 21, 20, 18, 17, 16, 15],
        "sleep": ["Less than 4", "4-5", "Less than 4", "Less than 4", "4-5", "Less than 4", "Less than 4"],
        "stress": ["Very high", "Very high", "Very high", "Very high", "Very high", "Very high", "Very high"],
        "weekly_workload": [24, 22],
        "weekly_climate": [34, 30],
        "monthly_motivation": [22, 20],
        "monthly_workload": [20, 18],
        "monthly_support": [30, 28],
        "monthly_recognition": [28, 26],
    },
}


def derive_condition(score: float) -> str:
    if score >= 85:
        return "Optimal"
    if score >= 70:
        return "Stable"
    if score >= 55:
        return "Strained"
    if score >= 40:
        return "High Risk"
    return "Critical"


def build_answer(question_id: str, answer_text: str, numeric_value: float, driver: str) -> Answer:
    return Answer(
        question_id=question_id,
        question_text=question_id,
        answer_text=answer_text,
        numeric_value=numeric_value,
        driver=driver,
    )


def build_daily_answers(preset: dict, index: int) -> list[Answer]:
    stress_text = preset["stress"][index]
    sleep_text = preset["sleep"][index]
    return [
        build_answer("dc_1", "Energy", float(preset["energy"][index]), "RC"),
        build_answer("dc_3", stress_text, float(preset["energy"][index]), "MR"),
        build_answer("dc_4", "Motivation", float(preset["motivation"][index]), "MC"),
        build_answer("dc_5", sleep_text, 0.0, "RC"),
        build_answer("dc_6", "Recovery", float(preset["recovery"][index]), "RC"),
    ]


def build_weekly_answers(preset: dict, index: int) -> list[Answer]:
    return [
        build_answer("wc_8", "Workload", float(preset["weekly_workload"][index]), "PA"),
        build_answer("wc_9", "Leadership Climate", float(preset["weekly_climate"][index]), "MC"),
    ]


def build_monthly_answers(preset: dict, index: int) -> list[Answer]:
    return [
        build_answer("mc_8", "Motivation", float(preset["monthly_motivation"][index]), "MC"),
        build_answer("mc_10", "Workload", float(preset["monthly_workload"][index]), "PA"),
        build_answer("mc_11", "Support", float(preset["monthly_support"][index]), "MC"),
        build_answer("mc_12", "Recognition", float(preset["monthly_recognition"][index]), "MC"),
    ]


def build_assessment_answers(dimensions: dict[str, float]) -> list[Answer]:
    return [
        build_answer("assessment_pc", "Physical Capacity", float(dimensions["PC"]), "PC"),
        build_answer("assessment_mr", "Mental Resilience", float(dimensions["MR"]), "MR"),
        build_answer("assessment_mc", "Morale & Cohesion", float(dimensions["MC"]), "MC"),
        build_answer("assessment_pa", "Purpose Alignment", float(dimensions["PA"]), "PA"),
        build_answer("assessment_rc", "Recovery Capacity", float(dimensions["RC"]), "RC"),
    ]


async def ensure_user(member: DemoMember) -> User:
    user = await User.find_one({"email": member.email})
    if user is None:
        user = User(
            email=member.email,
            hashed_password=DEMO_PASSWORD_HASH,
            name=member.name,
            organization_name=member.company,
            role=member.role,
            is_active=True,
            is_verified=True,
            onboarding_completed=True,
        )
        await user.insert()
        return user

    user.name = member.name
    user.organization_name = member.company
    user.role = member.role
    user.is_active = True
    user.is_verified = True
    user.onboarding_completed = True
    await user.save()
    return user


async def ensure_profile(user: User, member: DemoMember) -> None:
    profile = await Profile.find_one({"user_id": user.id})
    if profile is None:
        profile = Profile(
            user_id=user.id,
            name=member.name,
            age=member.age,
            gender=member.gender,
            company=member.company,
            department=member.department,
            team=member.team,
            role=member.role,
            height_cm=170.0,
            weight_kg=70.0,
            contact_number="+1-202-555-0100",
            employee_id=f"DEMO-{member.email.split('@')[0].replace('.', '-').upper()}",
            company_address=f"{member.company} Demo Campus",
            company_logo_url=None,
        )
        await profile.insert()
        return

    profile.name = member.name
    profile.age = member.age
    profile.gender = member.gender
    profile.company = member.company
    profile.department = member.department
    profile.team = member.team
    profile.role = member.role
    profile.height_cm = 170.0
    profile.weight_kg = 70.0
    profile.contact_number = "+1-202-555-0100"
    profile.employee_id = f"DEMO-{member.email.split('@')[0].replace('.', '-').upper()}"
    profile.company_address = f"{member.company} Demo Campus"
    profile.updated_at = datetime.utcnow()
    await profile.save()


async def clear_user_activity(user_id) -> None:
    db = get_database()
    for collection in ["checkins", "scores", "daily_checkins", "weekly_checkins", "monthly_checkins"]:
        await db[collection].delete_many({"user_id": user_id})


async def seed_user_activity(user: User, member: DemoMember) -> None:
    preset = PROFILE_PRESETS[member.template]
    now = datetime.utcnow()

    for index, overall in enumerate(preset["overall"]):
        timestamp = now - timedelta(days=6 - index)
        dimensions = {
            key: max(0.0, min(100.0, value + (index - 3)))
            for key, value in preset["dimensions"].items()
        }

        assessment = CheckIn(
            user_id=user.id,
            answers=build_assessment_answers(dimensions),
            submitted_at=timestamp,
        )
        await assessment.insert()

        score = Score(
            user_id=user.id,
            checkin_id=assessment.id,
            dimension_scores=DimensionScore(**dimensions),
            overall_score=float(overall),
            condition=derive_condition(float(overall)),
            created_at=timestamp,
        )
        await score.insert()

        daily = DailyCheckIn(
            user_id=user.id,
            answers=build_daily_answers(preset, index),
            submitted_at=timestamp,
        )
        await daily.insert()

    for index in range(2):
        timestamp = now - timedelta(days=7 * (2 - index))
        weekly = WeeklyCheckIn(
            user_id=user.id,
            answers=build_weekly_answers(preset, index),
            submitted_at=timestamp,
        )
        await weekly.insert()

    for index in range(2):
        timestamp = now - timedelta(days=30 * (2 - index))
        monthly = MonthlyCheckIn(
            user_id=user.id,
            answers=build_monthly_answers(preset, index),
            submitted_at=timestamp,
        )
        await monthly.insert()


async def seed_action_logs(user_lookup: dict[str, User]) -> None:
    db = get_database()
    await db["leader_action_logs"].delete_many({"note": {"$regex": r"^\[DEMO\]"}})

    action_specs = [
        ("ava.morgan@demo.dominion.ai", "Dominion Wellness Solutions", "Performance Operations", "OPS Strategy", "workload_strain", "Rebalanced workload across OPS Strategy", "[DEMO] Shifted noncritical deliverables and paused late-night escalation tickets."),
        ("ava.morgan@demo.dominion.ai", "Dominion Wellness Solutions", "Product", "AI Product", "high_stress", "Scheduled private stress check-ins", "[DEMO] Added 1:1 recovery check-ins for the AI Product pod."),
        ("noah.brooks@demo.dominion.ai", "Dominion Wellness Solutions", "Performance Operations", "Recovery Programs", "recovery_deficit", "Opened recovery reset block", "[DEMO] Protected two afternoons for coaching reset and reduced meeting load."),
        ("mia.patel@demo.dominion.ai", "Dominion Wellness Solutions", "Product", "AI Product", "morale_decline", "Launched morale pulse check", "[DEMO] Added weekly morale pulse and sprint-retro follow-up for product delivery."),
        ("ethan.scott@demo.dominion.ai", "Dominion Wellness Solutions", "Product", "Platform", "workload_strain", "Deferred lower priority roadmap items", "[DEMO] Paused two platform backlog items to reduce workload strain this cycle."),
        ("sophia.reed@demo.dominion.ai", "Dominion Wellness Solutions", "Client Success", "Customer Success", "fatigue", "Rotated customer escalations", "[DEMO] Rotated weekend escalation coverage to cut recurring fatigue for client success."),
        ("olivia.hart@demo.global.ai", "Global Tech Solutions", "Engineering", "Platform", "recovery_deficit", "Introduced meeting-free recovery block", "[DEMO] Reserved Friday afternoons for recovery and documentation catch-up."),
        ("liam.foster@demo.global.ai", "Global Tech Solutions", "Engineering", "Mobile", "fatigue", "Reduced after-hours deploy duty", "[DEMO] Moved late deploy ownership to an alternating rotation to reduce fatigue risk."),
        ("emma.diaz@demo.global.ai", "Global Tech Solutions", "Product Design", "UX Research", "morale_decline", "Started recognition sprint recap", "[DEMO] Added a recognition segment to design review to improve morale and visibility."),
        ("james.cole@demo.global.ai", "Global Tech Solutions", "Sales", "Enterprise Sales", "high_stress", "Added forecast coaching session", "[DEMO] Held a forecast coaching clinic after stress signals rose during quarter close."),
        ("benjamin.lee@demo.northstar.ai", "Northstar Health Group", "Regional Support", "North Region", "morale_decline", "Launched recognition ritual", "[DEMO] Added weekly recognition round-up and peer shout-outs."),
        ("harper.long@demo.northstar.ai", "Northstar Health Group", "Clinical Operations", "Care Delivery", "high_stress", "Simplified clinical handoff flow", "[DEMO] Streamlined handoff documentation to reduce stress during care transitions."),
        ("ella.turner@demo.northstar.ai", "Northstar Health Group", "Wellness Programs", "Program Delivery", "recovery_deficit", "Expanded recovery micro-break policy", "[DEMO] Introduced mandatory micro-breaks between community program sessions."),
        ("henry.ross@demo.northstar.ai", "Northstar Health Group", "Account Management", "Strategic Accounts", "workload_strain", "Reassigned overflow accounts", "[DEMO] Temporarily redistributed two strategic accounts to relieve workload strain."),
        ("ava.morgan@demo.dominion.ai", "Dominion Wellness Solutions", "Client Success", "Implementation", "fatigue", "Reduced after-hours support load", "[DEMO] Reassigned overnight implementation support for two weeks."),
        ("lucas.gray@demo.dominion.ai", "Dominion Wellness Solutions", "Client Success", "Implementation", "high_stress", "Escalated implementation support issue", "[DEMO] Flagged repeated launch-stress pattern to leadership for staffing review."),
        ("isla.bennett@demo.dominion.ai", "Dominion Wellness Solutions", "Sales", "Business Development", "morale_decline", "Introduced recognition scoreboard", "[DEMO] Published a visible weekly recognition scoreboard for the business development squad."),
        ("mason.clark@demo.dominion.ai", "Dominion Wellness Solutions", "Sales", "Partnerships", "other", "Documented stable partnership cadence", "[DEMO] Logged stable cadence and no further intervention required after partner review."),
        ("olivia.hart@demo.global.ai", "Global Tech Solutions", "Engineering", "Platform", "other", "Closed recovery follow-up", "[DEMO] Follow-up check showed recovery scores stabilized after protected focus time."),
        ("benjamin.lee@demo.northstar.ai", "Northstar Health Group", "Regional Support", "North Region", "other", "Closed recognition follow-up", "[DEMO] Recognition intervention completed and team pulse returned to stable."),
    ]

    total_specs = len(action_specs)
    for index, (email, organization, department, team, risk_key, action, note) in enumerate(action_specs):
        log = LeaderActionLog(
            leader_user_id=user_lookup[email].id,
            organization_name=organization,
            department=department,
            team=team,
            risk_key=risk_key,
            action=action,
            note=note,
            selected_from_recommended=True,
            created_at=datetime.utcnow() - timedelta(days=(total_specs - index)),
        )
        await log.insert()


async def seed_app_settings(superadmin: User | None) -> None:
    settings_payload = [
        (
            "privacy_policy",
            "Privacy Policy",
            "This demo environment contains fictional workforce wellness data for product review only.",
        ),
        (
            "terms_and_conditions",
            "Terms & Conditions",
            "Demo tenants may be reset at any time. No real employee data should be entered into this environment.",
        ),
        (
            "about_us",
            "About Us",
            "Dominion Wellness Solutions helps leadership teams monitor resilience, recovery, engagement, and burnout risk across organizations.",
        ),
    ]

    for key, title, content in settings_payload:
        setting = await AppSetting.find_one({"key": key})
        if setting is None:
            setting = AppSetting(
                key=key,
                title=title,
                content=content,
                updated_by_user_id=superadmin.id if superadmin is not None else None,
            )
            await setting.insert()
            continue

        setting.title = title
        setting.content = content
        setting.updated_by_user_id = superadmin.id if superadmin is not None else setting.updated_by_user_id
        setting.updated_at = datetime.utcnow()
        await setting.save()


async def ensure_superadmin_scope() -> User | None:
    superadmin = await User.find_one({"email": "superadmin@dominion.ai"})
    if superadmin is None:
        return None

    if superadmin.organization_name != "Dominion Wellness Solutions":
        superadmin.organization_name = "Dominion Wellness Solutions"
        await superadmin.save()
    return superadmin


async def main() -> None:
    await init_db()

    superadmin = await ensure_superadmin_scope()
    user_lookup: dict[str, User] = {}

    for member in DEMO_MEMBERS:
        user = await ensure_user(member)
        await ensure_profile(user, member)
        await clear_user_activity(user.id)
        await seed_user_activity(user, member)
        user_lookup[member.email] = user

    await seed_action_logs(user_lookup)
    await seed_app_settings(superadmin)

    print(f"Seeded {len(DEMO_MEMBERS)} demo users")
    print(f"Default demo password: {DEMO_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
