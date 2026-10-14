"""test_loader_templates.py — las plantillas descargables cargan tal cual y el comportamiento previo no cambia (decisión del autor, 5/10).
Uso: python test_loader_templates.py"""
import io
import tempfile
from pathlib import Path

import pandas as pd

import io_handler
import reporter


def _named(b: bytes, name: str):
    buf = io.BytesIO(b)
    buf.name = name
    return buf


def main() -> int:
    # 1. plantilla CSV (con 4 líneas de comentario) y plantilla Excel (con «Instrucciones» primero)
    for name, gen in (("plantilla.csv", reporter.generate_template_csv), ("plantilla.xlsx", reporter.generate_template_excel)):
        ld = io_handler.load_file(_named(gen(), name))
        s = io_handler.summarize_loaded(ld)
        assert ld.ghi_col == "GHI" and ld.temp_col == "temp_C" and s["has_temp"], (name, ld.ghi_col, ld.temp_col)
        assert s["n_rows"] in (9, 10), (name, s["n_rows"])
    print("[OK] las plantillas CSV y Excel cargan tal cual y detectan GHI y temp_C")

    # 2. el mismo CSV desde una ruta de archivo
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "con_comentarios.csv"
        p.write_bytes(reporter.generate_template_csv())
        ld = io_handler.load_file(p)
        assert ld.ghi_col == "GHI" and len(ld.df) == 9
    print("[OK] CSV con comentarios iniciales desde una ruta")

    # 3. sin comentarios iniciales el comportamiento no cambia (se compara con pandas directo)
    plain = "timestamp,GHI,temp_C\n2024-01-15 12:00:00,850.4,28.3\n2024-01-15 13:00:00,870.2,28.6\n"
    ld = io_handler.load_file(_named(plain.encode("utf-8"), "plano.csv"))
    ref = pd.read_csv(io.StringIO(plain))
    assert list(ld.df.columns[:3]) == list(ref.columns) and ld.df["GHI"].tolist() == ref["GHI"].tolist()
    print("[OK] CSV sin comentarios: igual que antes")

    # 4. un '#' dentro de los datos no se toca
    mid = "timestamp,GHI,nota\n2024-01-15 12:00:00,850.4,#a\n2024-01-15 13:00:00,870.2,b\n"
    ld = io_handler.load_file(_named(mid.encode("utf-8"), "medio.csv"))
    assert ld.df["nota"].tolist() == ["#a", "b"]
    print("[OK] un '#' dentro de los datos no se interpreta como comentario")

    # 5. Excel sin hoja «Plantilla»: se lee la primera hoja, como antes
    one = io.BytesIO()
    pd.DataFrame({"timestamp": ["2024-01-15 12:00:00", "2024-01-15 13:00:00"], "GHI": [850.4, 870.2]}).to_excel(one, sheet_name="Hoja1", index=False)
    one.seek(0)
    one.name = "una_hoja.xlsx"
    ld = io_handler.load_file(one)
    assert ld.ghi_col == "GHI" and len(ld.df) == 2
    print("[OK] Excel sin hoja «Plantilla»: se lee la primera hoja")

    # 6. CSV con comentarios pero sin GHI: sigue fallando con error explícito
    bad = "# solo comentario\n# otro\ntimestamp,otra\n2024-01-15 12:00:00,1\n"
    try:
        io_handler.load_file(_named(bad.encode("utf-8"), "malo.csv"))
        raise AssertionError("debía fallar sin columna GHI")
    except ValueError as e:
        assert "GHI" in str(e)
    print("[OK] sin columna GHI sigue fallando con error explícito")
    print("[OK] Todas las pruebas del cargador pasaron.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
