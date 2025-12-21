import whisperx
import torch
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal

class LyricsExtractorWhisperX(QObject):
    finished = pyqtSignal(str)   # ruta .lrc
    error    = pyqtSignal(str)
    progress = pyqtSignal(int)

    def __init__(self, params):
        super().__init__()
        self.p = params

    # ---------- helpers ----------
    def _format_time(self, seconds: float) -> str:
        mins  = int(seconds // 60)
        secs  = int(seconds % 60)
        cents = int((seconds % 1) * 100)
        return f"[{mins:02d}:{secs:02d}.{cents:02d}]"

    def _group_words(self, words):
        lines, current, last_end = [], [], 0
        for w in words:
            gap = w["start"] - last_end
            if gap > 0.2 and current:
                lines.append(" ".join(current))
                current = []
            current.append(w["word"])
            last_end = w["end"]
        if current:
            lines.append(" ".join(current))
        return lines

    def _insert_blanks(self, lines_data):
        out = []
        for i, (txt, start, end) in enumerate(lines_data):
            out.append((txt, start))
            if i < len(lines_data) - 1:
                nxt_start = lines_data[i+1][1]
                if nxt_start - end > 5 and out:
                    out.append(("", end + 0.01))
        return out
    # ---------- main ----------
    def run(self):
        try:
            self.progress.emit(10)
            device = "cuda" if torch.cuda.is_available() else "cpu"
            audio  = whisperx.load_audio(str(self.p.vocals_path))

            self.progress.emit(25)
            model = whisperx.load_model("large-v2", device, compute_type="float16",
                                        vad_options={"vad_model": None})
            result = model.transcribe(audio, language="es")

            self.progress.emit(50)
            align_model, align_meta = whisperx.load_align_model(language_code="es", device=device)
            result = whisperx.align(result, align_model, align_meta, audio, device)

            self.progress.emit(75)
            all_words = [w for seg in result["segments"] for w in seg["words"]]
            if not all_words:
                self.error.emit("No se detectaron palabras")
                return

            # cabecera
            header = ('<H1 style="color: #3AABEF;"><center>{}</center></H1>\n'
                      '<H2 style="color: #7E54AF;"><center>{}</center></H2>\n').format(
                          self.p.artist, self.p.song)

            # agrupar y cortar
            grouped = self._group_words(all_words)
            lines_data = []
            idx = 0
            for g in grouped:
                txt   = g
                start = all_words[idx]["start"]
                end   = all_words[idx + len(g.split()) - 1]["end"]
                lines_data.append((txt, start, end))
                idx += len(g.split())

            MIN_START = 0.5
            final_lines = [(txt, t) for txt, t in self._insert_blanks(lines_data) if t >= MIN_START]

            # ensamblar
            content = header
            for txt, t in final_lines:
                stamp = self._format_time(t)
                if txt == "":
                    content += f'{stamp}<center></center>\n'
                else:
                    content += f'{stamp}<center>{txt}</center>\n'

            with open(self.p.lrc_path, "w", encoding="utf-8") as f:
                f.write(content)

            self.progress.emit(100)
            self.finished.emit(str(self.p.lrc_path))

        except Exception as e:
            self.error.emit(str(e))