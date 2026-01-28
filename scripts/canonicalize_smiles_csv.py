#!/usr/bin/env python3
"""
Canoniza solo Parentsmiles en combined_dataset-14Dec2024.csv preservando estereoquímica.
Los fragmentos (Frag1smiles, Frag2smiles) se dejan sin cambios.

- Lee: public/authors/combined_dataset-14Dec2024.csv
- Escribe: public/authors/combined_dataset-14Dec2024_canonical.csv
- Columnas esperadas: Serial,Parentsmiles,Frag1smiles,Frag2smiles,BDE,BondType,Source

Uso:
  python3 scripts/canonicalize_smiles_csv.py
"""

import csv
import sys
from pathlib import Path

try:
    from rdkit import Chem
except ImportError:
    print("ERROR: rdkit no está instalado.", file=sys.stderr)
    print("Instálalo con: pip install rdkit-pypi", file=sys.stderr)
    sys.exit(1)

SRC = Path("public/authors/combined_dataset-14Dec2024.csv")
DST = Path("public/authors/combined_dataset-14Dec2024_canonical.csv")


def canon(smiles: str, preserve_stereo: bool = True) -> str:
    """Canoniza un SMILES preservando estereoquímica. Si falla, retorna original."""
    if not smiles:
        return ""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return smiles  # conserva original si es inválido
    try:
        return Chem.MolToSmiles(mol, isomericSmiles=preserve_stereo, canonical=True)
    except Exception:
        return smiles


def main():
    if not SRC.exists():
        print(f"ERROR: Input no encontrado: {SRC}", file=sys.stderr)
        sys.exit(1)

    print(f"Leyendo {SRC}...", file=sys.stderr)
    with SRC.open() as fin, DST.open("w", newline="") as fout:
        reader = csv.DictReader(fin)
        fieldnames = reader.fieldnames
        if not fieldnames:
            print("ERROR: CSV sin encabezados", file=sys.stderr)
            sys.exit(1)

        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()

        for i, row in enumerate(reader, start=1):
            # Solo canoniza Parentsmiles; fragmentos quedan igual
            row["Parentsmiles"] = canon(
                row.get("Parentsmiles", "").strip(), preserve_stereo=True
            )
            # Frag1smiles y Frag2smiles se dejan sin cambios
            writer.writerow(row)
            if i % 50000 == 0:
                print(f"  Procesadas {i} filas...", file=sys.stderr)

    print(f"✓ Listo. Escribí {DST}", file=sys.stderr)
    print(f"  Solo Parentsmiles fue canonizado (preservando estereoquímica)")
    print(f"  Frag1smiles y Frag2smiles se mantienen sin cambios")


if __name__ == "__main__":
    main()
