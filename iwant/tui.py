import questionary


def pick_model(models: list[str], message: str = "What do you want to launch?") -> str | None:
    return questionary.select(message, choices=models).ask()


def pick_autostop() -> int | None:
    """Returns idle-minutes-to-autostop, or None if the user cancelled the
    prompt (Ctrl+C/Esc) - NOT the same as choosing to disable autostop,
    which returns -1 (caller maps that to "no autostop")."""
    choice = questionary.select(
        "Autostop after how long idle?",
        choices=[
            questionary.Choice(title="30 minutes (default)", value=30),
            questionary.Choice(title="90 minutes (longer debug sessions)", value=90),
            questionary.Choice(title="180 minutes", value=180),
            questionary.Choice(title="Disable - I'll `iwant down` manually", value=-1),
        ],
        default=30,
    ).ask()
    return choice


def pick_infra(clouds: list[str]) -> str | None:
    """`clouds` are lowercase cloud keys (e.g. "gcp") that are already known
    to be enabled - see iwant/infra.py:enabled_infra(). There's no "disabled"
    option here: the SDK's sky.check() doesn't reliably expose why a cloud
    is disabled, so there's nothing useful to show for one.

    Always shows the prompt, even with a single choice (no special-casing
    "only one option" to auto-pick it) - the user still gets to see and
    confirm what's about to be used, same as every other picker here."""
    if not clouds:
        return None
    choices = [questionary.Choice(title=c.upper(), value=c) for c in clouds]
    return questionary.select("Where do you want to launch it?", choices=choices, default=clouds[0]).ask()


def pick_spot() -> bool | None:
    """Returns True for spot/preemptible, False for on-demand, or None if
    the user cancelled the prompt."""
    return questionary.select(
        "On-demand or spot?",
        choices=[
            questionary.Choice(title="On-demand (default, won't get reclaimed)", value=False),
            questionary.Choice(title="Spot (cheaper, can be reclaimed anytime)", value=True),
        ],
        default=False,
    ).ask()


def pick_running_instance(instances: list[dict], message: str) -> str | None:
    """`instances` are {"name": <cluster name>, "infra": ...} from
    sky_wrap.all_clusters() - infra is shown so the same model running on
    two different clouds isn't ambiguous in the picker."""
    choices = [
        questionary.Choice(
            title=f"{i['name']}" + (f"  ({i['infra']})" if i["infra"] else ""),
            value=i["name"],
        )
        for i in instances
    ]
    return questionary.select(message, choices=choices).ask()


def pick_setup_target(statuses: dict[str, bool]) -> str | None:
    """`statuses` maps cloud key -> enabled bool, e.g. from
    iwant/infra.py:check_all() (unlike pick_infra(), this always shows
    every curated cloud, disabled ones included - it's for `iwant setup`,
    where seeing what's *not* set up yet is the whole point)."""
    choices = [
        questionary.Choice(
            title=f"{c.upper():<12} {'enabled' if ok else 'not set up'}",
            value=c,
        )
        for c, ok in statuses.items()
    ]
    return questionary.select("Pick a cloud to see its setup status:", choices=choices).ask()


def pick_dry_run() -> bool | None:
    """Returns True for a dry run, False to launch for real, or None if the
    user cancelled the prompt."""
    return questionary.select(
        "Ready to launch?",
        choices=[
            questionary.Choice(title="Launch for real", value=False),
            questionary.Choice(title="Dry run only (show the plan, spend nothing)", value=True),
        ],
        default=False,
    ).ask()
