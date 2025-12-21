from dataclasses import dataclass
from pathlib import Path

@dataclass
class LyricsParams:
    vocals_path: Path
    lrc_path   : Path
    artist     : str
    song       : str
    model_name : str = "base"