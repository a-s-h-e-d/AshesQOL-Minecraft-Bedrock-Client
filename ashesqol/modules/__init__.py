from .base import Module
from .block_esp import BlockEsp
from .clickgui_theme import ClickGuiTheme
from .esp import Esp
from .freecam import Freecam
from .hud import Hud
from .nametags import Nametags
from .tracers import Tracers


def create_modules() -> list[Module]:
    """Every module, in the order shown in the control window. Add new ones here."""
    return [Hud(), Esp(), Tracers(), Nametags(), BlockEsp(), Freecam(), ClickGuiTheme()]
