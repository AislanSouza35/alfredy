from actions import mouse_actions


def test_obter_posicao_mouse(monkeypatch):
    def fake_get_cursor_pos(pointer):
        pointer._obj.x = 321
        pointer._obj.y = 654
        return True

    monkeypatch.setattr(mouse_actions._USER32, "GetCursorPos", fake_get_cursor_pos)

    assert mouse_actions.obter_posicao_mouse() == (321, 654)


def test_mover_mouse_para(monkeypatch):
    chamadas = []

    def fake_get_cursor_pos(pointer):
        pointer._obj.x = 10
        pointer._obj.y = 20
        return True

    def fake_set_cursor_pos(x, y):
        chamadas.append((x, y))
        return True

    monkeypatch.setattr(mouse_actions._USER32, "GetCursorPos", fake_get_cursor_pos)
    monkeypatch.setattr(mouse_actions._USER32, "GetSystemMetrics", lambda codigo: 1920 if codigo == 0 else 1080)
    monkeypatch.setattr(mouse_actions._USER32, "SetCursorPos", fake_set_cursor_pos)

    resultado = mouse_actions.mover_mouse_para(100, 200, duracao=0.05)

    assert "Mouse movido" in resultado
    assert chamadas
