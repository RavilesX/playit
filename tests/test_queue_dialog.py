"""Tests del diálogo "Administración de cola" (dialogs.PlaybackQueueDialog).

Usa un FakePlayer liviano en vez del fixture `player` (AudioPlayer completo):
el diálogo solo necesita `audio_player.play_queue` y `export_queue_mlst`.
"""
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest

from dialogs import PlaybackQueueDialog


class FakePlayer:
    def __init__(self, songs):
        self.play_queue = songs
        self.export_calls = 0

    def export_queue_mlst(self):
        self.export_calls += 1


def make_song(artist, duration="1:00", tags=""):
    return {"artist": artist, "song": "x", "duration": duration, "tags": tags}


def drag_row(table, app, src_center, dst_pos):
    QTest.mousePress(table.viewport(), Qt.MouseButton.LeftButton, pos=src_center)
    QTest.mouseMove(table.viewport(), pos=QPoint(src_center.x(), src_center.y() + 3))
    QTest.mouseMove(table.viewport(), pos=dst_pos)
    QTest.mouseRelease(table.viewport(), Qt.MouseButton.LeftButton, pos=dst_pos)
    app.processEvents()


class TestDragReorder:
    """Arrastrar una fila para reordenar (bug: la fila desaparecía en vez de
    reubicarse, por la limpieza automática del Drag & Drop nativo de Qt;
    ver _QueueTable.__doc__)."""

    def setup_dialog(self, app):
        fp = FakePlayer([make_song("A"), make_song("B"), make_song("C")])
        dialog = PlaybackQueueDialog(fp)
        dialog.show()
        return fp, dialog

    def test_arrastrar_al_final_no_borra_filas(self, app):
        fp, dialog = self.setup_dialog(app)
        t = dialog.table

        row0 = t.visualRect(t.model().index(0, 0)).center()
        last_rect = t.visualRect(t.model().index(2, 0))
        below_last = QPoint(last_rect.center().x(), last_rect.bottom() + 2)

        drag_row(t, app, row0, below_last)

        assert t.rowCount() == 3
        assert [s["artist"] for s in fp.play_queue] == ["B", "C", "A"]

    def test_arrastrar_al_principio(self, app):
        fp, dialog = self.setup_dialog(app)
        t = dialog.table

        row2 = t.visualRect(t.model().index(2, 0)).center()
        top_rect = t.visualRect(t.model().index(0, 0))
        target_top = QPoint(top_rect.center().x(), top_rect.top() + 1)

        drag_row(t, app, row2, target_top)

        assert t.rowCount() == 3
        assert [s["artist"] for s in fp.play_queue] == ["C", "A", "B"]

    def test_swap_filas_adyacentes(self, app):
        fp, dialog = self.setup_dialog(app)
        t = dialog.table

        row1 = t.visualRect(t.model().index(1, 0)).center()
        top_rect = t.visualRect(t.model().index(0, 0))
        target_top = QPoint(top_rect.center().x(), top_rect.top() + 1)

        drag_row(t, app, row1, target_top)

        assert t.rowCount() == 3
        assert [s["artist"] for s in fp.play_queue] == ["B", "A", "C"]

    def test_clic_simple_sin_arrastre_no_reordena(self, app):
        fp, dialog = self.setup_dialog(app)
        t = dialog.table
        row0 = t.visualRect(t.model().index(0, 0)).center()

        QTest.mousePress(t.viewport(), Qt.MouseButton.LeftButton, pos=row0)
        QTest.mouseRelease(t.viewport(), Qt.MouseButton.LeftButton, pos=row0)
        app.processEvents()

        assert [s["artist"] for s in fp.play_queue] == ["A", "B", "C"]

    def test_tags_sobreviven_al_arrastre(self, app):
        """Las celdas de Tags usan cellWidget (_TagsCell), no QTableWidgetItem:
        _move_row debe reubicarlas, no perderlas ni dejarlas vacías."""
        fp = FakePlayer([
            make_song("A", tags="rock"), make_song("B"), make_song("C", tags="bajo"),
        ])
        dialog = PlaybackQueueDialog(fp)
        dialog.show()
        t = dialog.table

        row0 = t.visualRect(t.model().index(0, 0)).center()
        last_rect = t.visualRect(t.model().index(2, 0))
        below_last = QPoint(last_rect.center().x(), last_rect.bottom() + 2)
        drag_row(t, app, row0, below_last)

        assert [s.get("tags") for s in fp.play_queue] == ["", "bajo", "rock"]

    def test_todas_las_filas_conservan_su_celda_de_tags_tras_varios_arrastres(self, app):
        """Regresión de un bug real: _move_row leía el song desde
        self.item(src, COL_SONG) DESPUÉS de haberlo sacado con takeItem, así
        que siempre daba None y ninguna fila arrastrada volvía a tener
        _TagsCell (ni el chip "+ tag"). _sync_order no lo detectaba porque
        lee la playlist, no la UI — por eso hace falta revisar el widget."""
        fp = FakePlayer([
            make_song("A", tags="rock"), make_song("B", tags="pop"),
            make_song("C", tags="bajo"), make_song("D", tags="otros"),
        ])
        dialog = PlaybackQueueDialog(fp)
        dialog.show()
        t = dialog.table

        for src, dst in [(0, 2), (1, 3), (2, 0), (3, 1)]:
            src_pos = t.visualRect(t.model().index(src, 0)).center()
            dst_rect = t.visualRect(t.model().index(dst, 0))
            dst_pos = QPoint(dst_rect.center().x(), dst_rect.top() + 1)
            drag_row(t, app, src_pos, dst_pos)

        for row in range(t.rowCount()):
            cell = t.cellWidget(row, dialog.COL_TAGS)
            assert cell is not None, f"fila {row} se quedó sin _TagsCell"
            add_chip = cell._layout.itemAt(cell._layout.count() - 2).widget()
            assert add_chip.label.text() == "+ tag", f"fila {row} sin botón + tag"
