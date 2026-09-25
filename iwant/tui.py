import questionary


def pick_model(models: list[str], message: str = "What do you want to launch?") -> str | None:
    return questionary.select(message, choices=models).ask()


def pick_autostop() -> int | None:
    """Idle minutes before autostop, -1 to disable it, or None if the user
    cancelled."""
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
    """`clouds` are enabled cloud keys (e.g. "gcp"). Asks even when there's
    only one, so the user sees where it's about to launch."""
    if not clouds:
        return None
    choices = [questionary.Choice(title=c.upper(), value=c) for c in clouds]
    return questionary.select("Where do you want to launch it?", choices=choices, default=clouds[0]).ask()


def pick_spot() -> bool | None:
    """True for spot, False for on-demand, None if cancelled."""
    return questionary.select(
        "On-demand or spot?",
        choices=[
            questionary.Choice(title="On-demand (default, won't get reclaimed)", value=False),
            questionary.Choice(title="Spot (cheaper, can be reclaimed anytime)", value=True),
        ],
        default=False,
    ).ask()


def pick_running_instance(instances: list[dict], message: str) -> str | None:
    """`instances` come from sky_wrap.all_clusters(); infra is shown so the
    same model on two clouds can be told apart."""
    choices = [
        questionary.Choice(
            title=f"{i['name']}" + (f"  ({i['infra']})" if i["infra"] else ""),
            value=i["name"],
        )
        for i in instances
    ]
    return questionary.select(message, choices=choices).ask()


def pick_setup_target(statuses: dict[str, bool]) -> str | None:
    """`statuses` maps every cloud to whether it's enabled (infra.check_all())."""
    choices = [
        questionary.Choice(
            title=f"{c.upper():<12} {'enabled' if ok else 'not set up'}",
            value=c,
        )
        for c, ok in statuses.items()
    ]
    return questionary.select("Pick a cloud to see its setup status:", choices=choices).ask()


def pick_dry_run() -> bool | None:
    """True for a dry run, False to launch for real, None if cancelled."""
    return questionary.select(
        "Ready to launch?",
        choices=[
            questionary.Choice(title="Launch for real", value=False),
            questionary.Choice(title="Dry run only (show the plan, spend nothing)", value=True),
        ],
        default=False,
    ).ask()
