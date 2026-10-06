from collections.abc import Sequence
from typing import Protocol, TypeVar

import questionary

from .records import CloudStatus, RunningCluster

SelectChoice = str | questionary.Choice
SelectDefault = str | questionary.Choice | None


class SelectPrompt(Protocol):
    def __call__(
        self, message: str, choices: Sequence[SelectChoice], default: SelectDefault = None
    ) -> questionary.Question: ...


select_prompt: SelectPrompt = questionary.select
Answer = TypeVar("Answer", str, int, bool)


def ask(question: questionary.Question, answer_type: type[Answer]) -> Answer | None:
    answer: object = question.ask()
    if answer is None:
        return None
    if not isinstance(answer, answer_type):
        raise TypeError(f"Expected a {answer_type.__name__} prompt answer")
    return answer


def pick_model(models: list[str], message: str = "What do you want to launch?") -> str | None:
    return ask(select_prompt(message, choices=models), str)


def pick_autostop() -> int | None:
    """Idle minutes before autostop, -1 to disable it, or None if the user
    cancelled."""
    default = questionary.Choice(title="30 minutes (default)", value=30)
    choice = select_prompt(
        "Autostop after how long idle?",
        choices=[
            default,
            questionary.Choice(title="90 minutes (longer debug sessions)", value=90),
            questionary.Choice(title="180 minutes", value=180),
            questionary.Choice(title="Disable - I'll `iwant down` manually", value=-1),
        ],
        default=default,
    )
    return ask(choice, int)


def pick_infra(clouds: list[str]) -> str | None:
    """`clouds` are enabled cloud keys (e.g. "gcp"). Asks even when there's
    only one, so the user sees where it's about to launch."""
    if not clouds:
        return None
    choices = [questionary.Choice(title=c.upper(), value=c) for c in clouds]
    return ask(select_prompt("Where do you want to launch it?", choices=choices, default=clouds[0]), str)


def pick_spot() -> bool | None:
    """True for spot, False for on-demand, None if cancelled."""
    default = questionary.Choice(title="On-demand (default, won't get reclaimed)", value=False)
    prompt = select_prompt(
        "On-demand or spot?",
        choices=[
            default,
            questionary.Choice(title="Spot (cheaper, can be reclaimed anytime)", value=True),
        ],
        default=default,
    )
    return ask(prompt, bool)


def pick_running_instance(instances: Sequence[RunningCluster], message: str) -> str | None:
    """`instances` come from sky_wrap.all_clusters(); infra is shown so the
    same model on two clouds can be told apart."""
    choices = [
        questionary.Choice(
            title=i.name + (f"  ({i.infra})" if i.infra else ""),
            value=i.name,
        )
        for i in instances
    ]
    return ask(select_prompt(message, choices=choices), str)


def pick_setup_target(statuses: Sequence[CloudStatus]) -> str | None:
    """Pick a cloud from its typed setup status records."""
    choices = [
        questionary.Choice(
            title=f"{status.name.upper():<12} {'enabled' if status.enabled else 'not set up'}",
            value=status.name,
        )
        for status in statuses
    ]
    return ask(select_prompt("Pick a cloud to see its setup status:", choices=choices), str)


def pick_dry_run() -> bool | None:
    """True for a dry run, False to launch for real, None if cancelled."""
    default = questionary.Choice(title="Launch for real", value=False)
    prompt = select_prompt(
        "Ready to launch?",
        choices=[
            default,
            questionary.Choice(title="Dry run only (show the plan, spend nothing)", value=True),
        ],
        default=default,
    )
    return ask(prompt, bool)
