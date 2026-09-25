import base64
import hashlib

# NEW: robust XML sanitization
import io
import logging
import re  # NEW: SVG sanitization
import xml.etree.ElementTree as ET
from typing import Any, Dict, Tuple, cast

import torch
from architecture import model
from attr import dataclass
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem.Draw import rdMolDraw2D

# NUEVO: para anotar posiciones en el lienzo
from rdkit.Geometry import rdGeometry

from api.controllers.cache_controller import cache_get, cache_set, init_cache_db
from api.model.dto import (
    Atom2D,
    BDEEvaluateRequest,
    Bond2D,
    DownloadReportRequest,
    DownloadReportResponseData,
    FragmentResponseData,
    InferAllRequest,
    InferAllResponseData,
    MoleculeInfoRequest,
    MoleculeInfoResponseData,
    MoleculeSmileCanonicalRequest,
    MoleculeSmileCanonicalResponseData,
    ObtainBDEFragmentsRequest,
    ObtainBDEFragmentsResponseData,
    PredictCheckRequest,
    PredictCheckResponseData,
    PredictedBond,
    PredictMultipleRequest,
    PredictMultipleResponseData,
    PredictSingleRequest,
    PredictSingleResponseData,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
from deepbde.architecture.inference_util import single_predict


@dataclass
class MoleculeInfo:
    """
    Información completa de una molécula generada a partir de SMILES.
    - molecule_id: ID único (hash SHA256)
    - smiles_canonical: SMILES canónico con H explícitos
    - canvas: Tamaño del lienzo para visualización
    - atoms: Diccionario con información 2D de átomos
    - bonds: Diccionario con información 2D de enlaces
    - image_svg: Representación SVG enriquecida de la molécula
    """

    mol: Chem.Mol
    molecule_id: str
    smiles_canonical: str
    canvas: Dict[str, int]
    atoms: Dict[str, Atom2D]
    bonds: Dict[str, Bond2D]
    image_svg: str


def generate_id_smiles(smiles: str) -> Tuple[Chem.Mol, str, str]:
    """Generates a unique ID and canonical SMILES representation for a molecule.
    Args:
        smiles (str): The SMILES representation of the molecule.
    Returns:
        Tuple[Chem.Mol, str, str]: Molecule object, unique ID, and canonical SMILES.
    """
    mol = None
    try:
        mol = Chem.MolFromSmiles(smiles)
    except Exception as e:
        raise ValueError(f"Invalid SMILES: {smiles}") from e
    if mol is None:
        raise ValueError(f"Invalid SMILES: {smiles}")
    Chem.SanitizeMol(mol)
    mol = Chem.AddHs(mol)
    smiles_canonical = Chem.MolToSmiles(
        mol, canonical=True, allHsExplicit=True, kekuleSmiles=True, isomericSmiles=True
    )
    mol = Chem.MolFromSmiles(smiles_canonical)
    Chem.SanitizeMol(mol)
    mol = Chem.AddHs(mol)
    smiles_canonical = Chem.MolToSmiles(
        mol, canonical=True, allHsExplicit=True, kekuleSmiles=True, isomericSmiles=True
    )
    mol_id = hashlib.sha256(smiles_canonical.encode()).hexdigest()[:16]
    return mol, mol_id, smiles_canonical


def verify_smiles(smiles: str, mol_id: str) -> bool:
    """
    Verifies if the provided molecule ID matches the generated ID from SMILES.
    Args:
        smiles (str): The SMILES representation of the molecule.
        mol_id (str): Unique ID to verify.
    Returns:
        bool: True if IDs match, raises ValueError otherwise.
    Raises:
        ValueError: If the SMILES is invalid or the ID does not match.
    """
    try:
        real_mol_id = generate_id_smiles(smiles)[1]
    except Exception as e:
        raise ValueError(f"Invalid SMILES: '{smiles}'. Error: {e}")
    if mol_id != real_mol_id:
        raise ValueError(
            f"Molecule ID does not match. SMILES: '{smiles}', Expected ID: '{real_mol_id}', Received ID: '{mol_id}'"
        )
    return True


def is_valid_for_bde(mol: MoleculeInfo, bond_idx: int) -> bool:
    """
    Checks if a bond at the given index is a single, non-cyclic bond.
    Only single, non-cyclic bonds are valid for BDE prediction because the model is trained on such cases and cyclic bonds have different dissociation behavior.
    Args:
        mol (MoleculeInfo): The molecule information object.
        bond_idx (int): The index of the bond to check.
    Returns:
        bool: True if the bond is single and not in a ring, False otherwise.
    Raises:
        ValueError: If the bond index is out of range.
    """
    if bond_idx < 0 or bond_idx >= mol.GetNumBonds():  # pyright: ignore[reportAttributeAccessIssue]
        raise ValueError(
            f"Bond index {bond_idx} out of range for molecule with {mol.GetNumBonds()} bonds"
        )  # pyright: ignore[reportAttributeAccessIssue]
    bond = mol.GetBondWithIdx(bond_idx)  # type: ignore
    return bond.GetBondType() == Chem.BondType.SINGLE and not bond.IsInRing()


def calculate_canvas_size(
    mol: Chem.Mol, padding: int = 50, min_size: int = 300
) -> Dict[str, int]:
    """Calculates the canvas size based on the molecule's bounding box.
    Args:
        mol (Chem.Mol): The RDKit molecule object with 2D coordinates.
        padding (int): Padding to add around the molecule.
        min_size (int): Minimum width and height of the canvas.
    Returns:
        Dict[str, int]: Dictionary with 'width' and 'height' keys.
    """
    conf = mol.GetConformer()
    positions = [conf.GetAtomPosition(i) for i in range(mol.GetNumAtoms())]  # type: ignore[attr-defined]
    min_x, max_x = min(pos.x for pos in positions), max(pos.x for pos in positions)  # type: ignore[attr-defined]
    min_y, max_y = min(pos.y for pos in positions), max(pos.y for pos in positions)  # type: ignore[attr-defined]
    width = int(max_x - min_x) + padding  # type: ignore[attr-defined]
    height = int(max_y - min_y) + padding  # type: ignore[attr-defined]
    return {"width": max(width, min_size), "height": max(height, min_size)}


# REPLACE: sanitize RDKit SVG to standard <svg xmlns="http://www.w3.org/2000/svg"> without ns0/svg prefixes
def sanitize_svg_text(svg: str) -> str:
    s = svg.strip()
    # Try robust namespace stripping via ElementTree
    try:
        it = ET.iterparse(io.StringIO(s))
        for _, el in it:
            # Strip namespaces from tag
            if isinstance(el.tag, str) and el.tag.startswith("{"):
                el.tag = el.tag.split("}", 1)[1]
            # Strip namespaces from attributes
            if el.attrib:
                new_attrib = {}
                for k, v in el.attrib.items():
                    if isinstance(k, str) and k.startswith("{"):
                        k = k.split("}", 1)[1]
                    new_attrib[k] = v
                el.attrib.clear()
                el.attrib.update(new_attrib)
        root = it.root  # type: ignore
        out = ET.tostring(root, encoding="unicode")
        # Ensure default SVG namespace on root
        if "xmlns=" not in out:
            out = re.sub(
                r"<svg\b", '<svg xmlns="http://www.w3.org/2000/svg"', out, count=1
            )
        # Single-line
        out = "".join(out.splitlines()).strip()
        # NEW: unescape escaped quotes/newlines if present
        out = out.replace('\\"', '"').replace("\\'", "'").replace("\\n", "")
        # NUEVO: usar comillas simples en atributos para evitar escapes en JSON
        out = re.sub(r'="([^"]*)"', r"='\1'", out)
        return out
    except Exception:
        # Fallback to regex-based cleanup
        s = re.sub(
            r"<(/?)ns\d+:", r"<\1", s
        )  # <ns0:tag> -> <tag>, </ns0:tag> -> </tag>
        s = re.sub(r"<svg:svg\b", "<svg", s)  # <svg:svg> -> <svg>
        s = s.replace("</svg:svg>", "</svg>")  # </svg:svg> -> </svg>
        s = re.sub(r'\s+xmlns:ns\d+="[^"]*"', "", s)  # remove xmlns:nsX="..."
        s = re.sub(r'\s+xmlns:svg="[^"]*"', "", s)  # remove xmlns:svg="..."
        if "xmlns=" not in s:
            s = s.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
        s = "".join(s.splitlines()).strip()
        # NEW: unescape escaped quotes/newlines if present
        s = s.replace('\\"', '"').replace("\\'", "'").replace("\\n", "")
        # NUEVO: usar comillas simples en atributos para evitar escapes en JSON
        s = re.sub(r'="([^"]*)"', r"='\1'", s)
        return s


def generate_molecule_svg(
    mol: Chem.Mol, canvas: Dict[str, int]
) -> Tuple[str, rdMolDraw2D.MolDraw2DSVG]:
    """Generates an SVG representation of the molecule with atom and bond indices in the default color.
    Args:
        mol (Chem.Mol): The RDKit molecule object with 2D coordinates.
        canvas (Dict[str, int]): Dictionary with 'width' and 'height' of the canvas.
    Returns:
        Tuple[str, rdMolDraw2D.MolDraw2DSVG]: SVG string of the molecule drawing and the drawer object.
    """
    drawer = rdMolDraw2D.MolDraw2DSVG(canvas["width"], canvas["height"])
    opts = drawer.drawOptions()
    opts.addStereoAnnotation = True
    opts.explicitMethyl = True
    opts.includeAtomTags = True
    opts.addAtomIndices = False  # Desactivar índices de átomos
    opts.addBondIndices = (
        True  # Enable bond indices in the default color (typically black)
    )
    drawer.DrawMolecule(mol)  # type: ignore[attr-defined]
    drawer.FinishDrawing()
    raw_svg = drawer.GetDrawingText()

    return sanitize_svg_text(raw_svg), drawer


def generate_bde_svg_for_bonds(mol: Chem.Mol, bonds_to_label: list[int], bde_map: Dict[int, float | None]) -> Tuple[str, Dict[str, int]]:
    """
    Dibuja la molécula y anota sobre el lienzo únicamente los enlaces solicitados,
    mostrando el BDE en un recuadro encima del enlace (sin índices de enlace).
    """
    # Asegurar coords 2D y tamaño del canvas
    AllChem.Compute2DCoords(mol)  # pyright: ignore[reportAttributeAccessIssue]
    canvas = calculate_canvas_size(mol)

    drawer = rdMolDraw2D.MolDraw2DSVG(canvas["width"], canvas["height"])
    opts = drawer.drawOptions()
    opts.addStereoAnnotation = True
    opts.explicitMethyl = True
    opts.includeAtomTags = True
    opts.addAtomIndices = False  # Desactivar índices de átomos
    opts.addBondIndices = False  # No mostrar índices de enlace

    drawer.DrawMolecule(mol)  # type: ignore[attr-defined]

    # Calcular tamaño de fuente dinámico basado en el tamaño del canvas y la escala de anotación
    # RDKit usa annotationFontScale (default ~0.5) relativo al tamaño de fuente base
    base_font_size = opts.annotationFontScale * 12  # Escala base aproximada
    # Ajustar según el tamaño del canvas (normalizar a un canvas ~300px)
    scale_factor = min(canvas["width"], canvas["height"]) / 300.0
    dynamic_font_size = base_font_size * scale_factor * 0.75  # 3/4 del tamaño original
    # Limitar tamaño de fuente entre valores razonables
    dynamic_font_size = max(6, min(dynamic_font_size, 12))

    # Construir overlays de BDE (rect + text) para mayor legibilidad
    overlays: list[str] = []
    for b_idx in bonds_to_label or []:
        if b_idx < 0 or b_idx >= mol.GetNumBonds():
            continue
        bde = bde_map.get(b_idx, None)
        label = f"{float(bde):.1f}" if isinstance(bde, (float, int)) else ""

        bond = mol.GetBondWithIdx(b_idx)
        a1 = bond.GetBeginAtomIdx()
        a2 = bond.GetEndAtomIdx()
        p1 = drawer.GetDrawCoords(a1)
        p2 = drawer.GetDrawCoords(a2)

        # Punto medio del enlace
        mx, my = (p1.x + p2.x) / 2.0, (p1.y + p2.y) / 2.0

        # Desplazar un poco en la normal del enlace para no tapar la línea
        vx, vy = (p2.x - p1.x), (p2.y - p1.y)
        norm = (vx**2 + vy**2) ** 0.5 or 1.0
        nx, ny = -vy / norm, vx / norm  # normal
        off = 6.0
        cx, cy = mx + nx * off, my + ny * off  # centro del label
        if(label != ""):
            # Tamaño del rectángulo en función del texto y tamaño de fuente dinámico
            char_width = dynamic_font_size * 0.6  # Ancho aproximado por carácter
            w = max(
                dynamic_font_size * 2, char_width * len(label) + dynamic_font_size * 0.5
            )  # ancho proporcional
            h = dynamic_font_size * 1.3  # altura proporcional
            x = cx - w / 2
            y = cy - h / 2

            # Rectángulo de fondo y texto centrado (comillas simples para evitar escapes en JSON)
            overlay = (
                f"<rect x='{x}' y='{y}' width='{w}' height='{h}' "
                f"fill='white' fill-opacity='0.9' stroke='#1a1a1a' stroke-width='0.3' />"
                f"<text x='{cx}' y='{cy + 1}' text-anchor='middle' dominant-baseline='middle' "
                f"font-family='Arial, sans-serif' font-size='{dynamic_font_size}' fill='#0033cc' font-weight='bold'>{label}</text>"
            )
            overlays.append(overlay)

    drawer.FinishDrawing()
    raw_svg = drawer.GetDrawingText()

    # Sanitizar y luego insertar overlays antes del cierre </svg>
    svg_clean = sanitize_svg_text(raw_svg)
    if overlays:
        insertion = "".join(overlays)
        end = svg_clean.rfind("</svg>")
        if end != -1:
            svg_clean = svg_clean[:end] + insertion + svg_clean[end:]
    # NUEVO: re-sanitizar para normalizar comillas y namespaces también en overlays
    svg_clean = sanitize_svg_text(svg_clean)
    return svg_clean, canvas

def get_atoms_info(mol: Chem.Mol, drawer: rdMolDraw2D.MolDraw2DSVG) -> Dict[str, Atom2D]:
    """Extracts atom information from the molecule.
    Args:
        mol (Chem.Mol): The RDKit molecule object.
        drawer (rdMolDraw2D.MolDraw2DSVG): The RDKit SVG drawer object.
    Returns:
        Dict[str, Atom2D]: Dictionary mapping atom indices to Atom2D objects.
    """
    atoms = {}
    for atom in mol.GetAtoms():
        idx = atom.GetIdx()
        pt = drawer.GetDrawCoords(idx)
        symbol = atom.GetSymbol()
        atom_smiles = Chem.MolToSmiles(Chem.MolFromSmiles(f'[{symbol}]')) if symbol else None
        atoms[str(idx)] = Atom2D(
            x=float(pt.x),
            y=float(pt.y),
            symbol=symbol,
            smiles=atom_smiles
        )
    return atoms
def get_bonds_info(mol: Chem.Mol, drawer: rdMolDraw2D.MolDraw2DSVG) -> Dict[str, Bond2D]:
    """Extracts bond information from the molecule.
    Args:
        mol (Chem.Mol): The RDKit molecule object.
        drawer (rdMolDraw2D.MolDraw2DSVG): The RDKit SVG drawer object.
    Returns:
        Dict[str, Bond2D]: Dictionary mapping bond indices to Bond2D objects.
    """
    bonds = {}
    for bond in mol.GetBonds():
        b_idx = bond.GetIdx()
        start_idx = bond.GetBeginAtomIdx()
        end_idx = bond.GetEndAtomIdx()
        start_pt = drawer.GetDrawCoords(start_idx)
        end_pt = drawer.GetDrawCoords(end_idx)
        atom1 = mol.GetAtomWithIdx(start_idx)
        atom2 = mol.GetAtomWithIdx(end_idx)
        bond_type = bond.GetBondType()
        bond_type_map = {
            Chem.BondType.SINGLE: "single",
            Chem.BondType.DOUBLE: "double",
            Chem.BondType.TRIPLE: "triple",
            Chem.BondType.AROMATIC: "aromatic"
        }
        bond_type_str = bond_type_map.get(bond_type, str(bond_type).lower())
        bond_atoms = f"{atom1.GetSymbol()}-{atom2.GetSymbol()}"
        bonds[str(b_idx)] = Bond2D(
            start=start_idx,
            end=end_idx,
            start_coords={"x": float(start_pt.x), "y": float(start_pt.y)},
            end_coords={"x": float(end_pt.x), "y": float(end_pt.y)},
            bond_atoms=bond_atoms,
            bond_type=bond_type_str if bond_type_str in {"single", "double", "triple", "aromatic"} else "single"  # type: ignore
        )
    return bonds
def get_all_info_molecule(smiles: str) -> MoleculeInfo:
    """
    Extracts all relevant information from a molecule given its SMILES representation.
    Sanitizes and validates the SMILES before processing.
    Args:
        smiles (str): The SMILES representation of the molecule.
    Returns:
        MoleculeInfo: An object containing all relevant information about the molecule.
    Raises:
        ValueError: If the SMILES is invalid.
    """
    cached = cache_get(f"info_{smiles}")
    if cached is not None:
        return cached
    try:
        mol, mol_id, smiles_canonical = generate_id_smiles(smiles)
    except Exception as e:
        raise ValueError(f"Invalid SMILES: '{smiles}'. Error: {e}")
    AllChem.Compute2DCoords(mol) # pyright: ignore[reportAttributeAccessIssue]
    canvas = calculate_canvas_size(mol)
    image_svg, drawer = generate_molecule_svg(mol, canvas)
    atoms = get_atoms_info(mol, drawer)
    bonds = get_bonds_info(mol, drawer)
    assert len(atoms) == mol.GetNumAtoms(), f"Atom count mismatch: expected {mol.GetNumAtoms()}, got {len(atoms)}"
    assert len(bonds) == mol.GetNumBonds(), f"Bond count mismatch: expected {mol.GetNumBonds()}, got {len(bonds)}"
    info = MoleculeInfo(
        mol=mol,
        molecule_id=mol_id,
        smiles_canonical=smiles_canonical,
        canvas=canvas,
        atoms=atoms,
        bonds=bonds,
        image_svg=image_svg
    )
    cache_set(f"info_{smiles}", info)
    return info
def molecule_info_controller(request: MoleculeInfoRequest) -> MoleculeInfoResponseData:
    """Controller for predicting the bond dissociation energy (BDE) of a molecule.
    Args:
        request (PredictRequest): Request object containing the SMILES string.
    Returns:
        PredictResponseData: Response containing molecule data and SVG.
    """
    all_info = get_all_info_molecule(request.smiles)
    return MoleculeInfoResponseData(
        smiles_canonical=all_info.smiles_canonical,
        image_svg=all_info.image_svg,
        canvas=all_info.canvas,
        atoms=all_info.atoms,
        bonds=all_info.bonds,
        molecule_id=all_info.molecule_id
    )
def get_bde_for_bond_indices(mol_info: MoleculeInfo, idx: int ) -> float | None:
    """Predicts the bond dissociation energy (BDE) for a specific bond index in a molecule.
    Args:
        smiles (str): The SMILES representation of the molecule.
        idx (int): The index of the bond to predict.
    Returns:
        float: The predicted BDE for the specified bond.
    """
    cache_key = f"bde_{mol_info.molecule_id}_{idx}"
    cached = cache_get(cache_key)
    if isinstance(cached, (float, int)):
        return cached
    if not is_valid_for_bde(mol_info.mol, idx):
        return None
    bde = single_predict(mol_info.smiles_canonical, idx)
    bde_val = bde.item() if isinstance(bde, torch.Tensor) else bde
    cache_set(cache_key, bde_val)
    return bde_val


def predict_single_controller(request: PredictSingleRequest) -> PredictSingleResponseData:
    """
    Controller para la predicción de BDE de un único enlace de una molécula.
    Args:
        request (PredictSingleRequest): Contiene el SMILES, el ID de la molécula y el índice del enlace.
    Returns:
        PredictSingleResponseData: Contiene el SMILES canónico y la predicción del enlace.
    """
    cache_key = f"single_{request.smiles}_{request.molecule_id}_{request.bond_idx}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    all_info = get_all_info_molecule(request.smiles)
    verify_smiles(all_info.smiles_canonical, request.molecule_id)
    mol = all_info.mol
    if not is_valid_for_bde(mol, request.bond_idx):
        raise ValueError(f"Bond index {request.bond_idx} is not a single bond or is in a ring.")
    bond = mol.GetBondWithIdx(request.bond_idx)
    begin_idx = bond.GetBeginAtomIdx()
    end_idx = bond.GetEndAtomIdx()
    atom1 = mol.GetAtomWithIdx(begin_idx)
    atom2 = mol.GetAtomWithIdx(end_idx)
    bde = get_bde_for_bond_indices(all_info, request.bond_idx)
    predicted_bond = PredictedBond(
        idx=request.bond_idx,
        bde=bde,
        begin_atom_idx=begin_idx,
        end_atom_idx=end_idx,
        bond_atoms=f"{atom1.GetSymbol()}-{atom2.GetSymbol()}",
        bond_type=bond.GetBondType().name.lower(),
        is_fragmentable=bde is not None
    )
    result = PredictSingleResponseData(
        smiles_canonical=all_info.smiles_canonical,
        bond=predicted_bond
    )
    cache_set(cache_key, result)
    return result
def predict_multiple_controller(request: PredictMultipleRequest) -> PredictMultipleResponseData:
    """
    Controller para la predicción de BDE de múltiples enlaces de una molécula.
    Args:
        request (PredictMultipleRequest):
            - smiles (str): SMILES de la molécula.
            - bond_indices (List[int]): Lista de índices de enlaces a predecir.
    Returns:
        PredictMultipleResponseData: Respuesta con la lista de enlaces y sus BDEs predichos.
    """
    indices_key = ','.join(map(str, request.bond_indices)) if request.bond_indices else ''
    cache_key = f"multi_{request.smiles}_{request.molecule_id}_{indices_key}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    all_info = get_all_info_molecule(request.smiles)
    verify_smiles(all_info.smiles_canonical, request.molecule_id)
    predicted_bonds = []
    for idx in request.bond_indices:
        if not is_valid_for_bde(all_info.mol, idx):
            raise ValueError(f"Bond index {idx} is not a single bond or is in a ring.")
        bde = get_bde_for_bond_indices(all_info, idx)
        bond = all_info.mol.GetBondWithIdx(idx)
        begin_idx = bond.GetBeginAtomIdx()
        end_idx = bond.GetEndAtomIdx()
        atom1 = all_info.mol.GetAtomWithIdx(begin_idx)
        atom2 = all_info.mol.GetAtomWithIdx(end_idx)
        predicted_bond = PredictedBond(
            idx=idx,
            bde=bde,
            begin_atom_idx=begin_idx,
            end_atom_idx=end_idx,
            bond_atoms=f"{atom1.GetSymbol()}-{atom2.GetSymbol()}",
            bond_type=bond.GetBondType().name.lower(),
            is_fragmentable=bde is not None
        )
        predicted_bonds.append(predicted_bond)
    result = PredictMultipleResponseData(
        smiles=request.smiles,
        molecule_id=request.molecule_id,
        bonds=predicted_bonds
    )
    cache_set(cache_key, result)
    return result
def infer_all_controller(request: InferAllRequest) -> InferAllResponseData:
    """
    Controller para inferir la BDE de todos los enlaces posibles de una molécula.
    Args:
        request (InferAllRequest): Contiene el SMILES de la molécula.
    Returns:
        InferAllResponseData: Respuesta con la lista de enlaces y sus BDEs predichos o null si no se pueden predecir.
    """
    cache_key = f"infer_{request.smiles}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    all_info = get_all_info_molecule(request.smiles)
    mol = all_info.mol
    predicted_bonds = []
    for bond in mol.GetBonds():
        bond_idx = bond.GetIdx()
        begin_idx = bond.GetBeginAtomIdx()
        end_idx = bond.GetEndAtomIdx()
        atom1 = mol.GetAtomWithIdx(begin_idx)
        atom2 = mol.GetAtomWithIdx(end_idx)
        if is_valid_for_bde(mol, bond_idx):
            bde = get_bde_for_bond_indices(all_info, bond_idx)
        else:
            bde = None
        predicted_bond = PredictedBond(
            idx=bond_idx,
            bde=bde,
            begin_atom_idx=begin_idx,
            end_atom_idx=end_idx,
            bond_atoms=f"{atom1.GetSymbol()}-{atom2.GetSymbol()}",
            bond_type=bond.GetBondType().name.lower(),
            is_fragmentable=bde is not None
        )
        predicted_bonds.append(predicted_bond)
    result = InferAllResponseData(
        smiles_canonical=all_info.smiles_canonical,
        molecule_id=all_info.molecule_id,
        bonds=predicted_bonds
    )
    cache_set(cache_key, result)
    return result
def get_fragments_from_bond(mol: Chem.Mol, bond_idx: int) -> list[str]:
    """Gets the two fragments generated by breaking a bond in a molecule.
    Args:
        mol (Chem.Mol): The RDKit molecule object.
        bond_idx (int): The index of the bond to break.
    Returns:
        list[str]: A list of SMILES strings for the two fragments.
    """
    cache_key = f"frag_{Chem.MolToSmiles(mol, canonical=True)}_{bond_idx}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        mol_copy = Chem.RWMol(mol)
        bond = mol_copy.GetBondWithIdx(bond_idx)
        begin_idx = bond.GetBeginAtomIdx()
        end_idx = bond.GetEndAtomIdx()
        
        # Verificar si uno de los átomos es hidrógeno
        atom1 = mol_copy.GetAtomWithIdx(begin_idx)
        atom2 = mol_copy.GetAtomWithIdx(end_idx)
        
        mol_copy.RemoveBond(begin_idx, end_idx)
        fragments = Chem.GetMolFrags(mol_copy, asMols=True)
        
        result = []
        for frag in fragments:
            frag_smiles = Chem.MolToSmiles(frag, canonical=True)
            
            # Corregir fragmentos de hidrógeno problemáticos
            if frag_smiles == "[HH]" or frag_smiles == "H" or (frag.GetNumAtoms() == 1 and frag.GetAtomWithIdx(0).GetSymbol() == "H"):
                # Si es un fragmento de un solo hidrógeno, representarlo como radical
                result.append("[H]")
            else:
                result.append(frag_smiles)
        
        cache_set(cache_key, result)
        return result
    except Exception as e:
        logger.error(f"Error fragmenting bond {bond_idx}: {e}")
        return []
def  report_txt(smile:str) -> str:
    """Generates a report in text format for the molecule.
    Args:
        smile (str): The SMILES representation of the molecule.
    Returns:
        str: Text report of the molecule.
    """
    # El txt debe tener el smile introducido el id, todas las bde 
    # y que enlaces se selecciono y que moleculas da como resultado al romper el enlace.
    try:
        all_info = get_all_info_molecule(smile)
    except Exception as e:
        logger.error(f"Error processing SMILES '{smile}': {e}")
        return f"Error: Invalid SMILES ({smile}). Detail: {e}"
    report_lines = [
        f"SMILE introduced: {smile}",
        f"SMILES canonical with hs: {all_info.smiles_canonical}",
        "Bonds and BDEs:"
    ]
    for bond in all_info.mol.GetBonds():
        bond_idx = bond.GetIdx()
        begin_idx = bond.GetBeginAtomIdx()
        end_idx = bond.GetEndAtomIdx()
        atom1 = all_info.mol.GetAtomWithIdx(begin_idx)
        atom2 = all_info.mol.GetAtomWithIdx(end_idx)
        bde = get_bde_for_bond_indices(all_info, bond_idx)
        report_lines.append(
            f"Bond {bond_idx}: {atom1.GetSymbol()}-{atom2.GetSymbol()} (BDE: {bde})"
        )
    report_lines.append("Fragmentation results:")
    for bond in all_info.mol.GetBonds():
        bond_idx = bond.GetIdx()
        bde = get_bde_for_bond_indices(all_info, bond_idx)
        if bde is not None:
            fragments = get_fragments_from_bond(all_info.mol, bond_idx)
            report_lines.append(
                f"Fragment from bond {bond_idx}: (BDE: {bde})"
            )
            if len(fragments) == 2:
                report_lines.append(f"Generated fragments: {fragments[0]} and {fragments[1]}")
            else:
                report_lines.append(f"Invalid fragmentation for bond {bond_idx}")
    report_lines="\n".join(report_lines)
    logger.info("Generated report:\n%s", report_lines)    
    return report_lines
def download_report_controller(request: DownloadReportRequest) -> DownloadReportResponseData:
    """Generates and downloads a report for the molecule with all information of BDE and fragments.
    Args:
        request (DownloadReportRequest): Request object with SMILES and format.
    Returns:
        DownloadReportResponseData: Response with base64-encoded report.
    """
    report_base64 = ""
    if request.format not in { "txt"}:
        raise ValueError("Unsupported format: use 'txt'.")
    if request.format == "txt":
        report_content = report_txt(request.smiles)
        report_base64 = base64.b64encode(report_content.encode('utf-8')).decode('utf-8')
    return DownloadReportResponseData(
        type="txt",
        report_base64=report_base64
    )
def predict_check_controller(request: PredictCheckRequest) -> PredictCheckResponseData: #ignore
    try:
        all_info = get_all_info_molecule(request.smiles)
        verify_smiles(all_info.smiles_canonical, request.molecule_id)
        if not is_valid_for_bde(all_info.mol, request.bond_idx):
            raise ValueError(f"Bond index {request.bond_idx} does not correspond to a single non-cyclic bond.")
    except Exception as e:
        logger.error(f"Error in predict_check_controller: {e}")
        raise ValueError(f"Validation error: {e}")
    # Construct a safe cache key using all relevant request parameters
    products_key = ','.join(map(str, request.products)) if request.products else ''
    cache_key = f"check_{request.smiles}_{request.molecule_id}_{request.bond_idx}_{products_key}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    mol = all_info.mol
    bond_idx = request.bond_idx
    bond = mol.GetBondWithIdx(bond_idx)
    begin_idx = bond.GetBeginAtomIdx()
    end_idx = bond.GetEndAtomIdx()
    atom1 = mol.GetAtomWithIdx(begin_idx)
    atom2 = mol.GetAtomWithIdx(end_idx)
    bde = get_bde_for_bond_indices(all_info, bond_idx)
    predicted_bond = PredictedBond(
        idx=bond_idx,
        bde=bde,
        begin_atom_idx=begin_idx,
        end_atom_idx=end_idx,
        bond_atoms=f"{atom1.GetSymbol()}-{atom2.GetSymbol()}",
        bond_type=bond.GetBondType().name.lower(),
        is_fragmentable=bde is not None
    )
    # Validate input products are valid SMILES
    invalid_smiles = [s for s in request.products if Chem.MolFromSmiles(s) is None]
    if invalid_smiles:
        logger.error(f"Invalid SMILES in products: {invalid_smiles}")
        raise ValueError(f"One or more products are not valid SMILES: {invalid_smiles}")
    # Get generated products (fragments)
    products = get_fragments_from_bond(mol, bond_idx)
    products_canonical = [Chem.MolToSmiles(Chem.MolFromSmiles(s), canonical=True, allHsExplicit=True, kekuleSmiles=True, isomericSmiles=True) for s in products if Chem.MolFromSmiles(s) is not None]
    input_products_canonical = [Chem.MolToSmiles(Chem.MolFromSmiles(s), canonical=True, allHsExplicit=True, kekuleSmiles=True, isomericSmiles=True) for s in request.products if Chem.MolFromSmiles(s) is not None]
    if bde is None or not products_canonical:
        result = PredictCheckResponseData(
            smiles_canonical=all_info.smiles_canonical,
            bond=predicted_bond,
            are_same_products=False,
            products=["incompatible bond"]
        )
        cache_set(cache_key, result)
        return result
    are_same_products = set(products_canonical) == set(input_products_canonical)
    result = PredictCheckResponseData(
        smiles_canonical=all_info.smiles_canonical,
        bond=predicted_bond,
        are_same_products=are_same_products,
        products=products_canonical
    )
    cache_set(cache_key, result)
    return result
def molecule_smile_canonical_controller(smiles: MoleculeSmileCanonicalRequest) -> MoleculeSmileCanonicalResponseData:
    """Generates the canonical SMILES for a given molecule.
    Args:
        smiles (MoleculeSmileCanonicalRequest): Request object containing the SMILES string.
    Returns:
        MoleculeSmileCanonicalResponseData: Response containing the canonical SMILES.
    """
    try:
        _, mol_id, smiles_canonical = generate_id_smiles(smiles.smiles)
        return MoleculeSmileCanonicalResponseData(
            smiles=smiles.smiles,
            smiles_canonical=smiles_canonical,
            molecule_id=mol_id
        )
    except ValueError as e:
        raise ValueError(f"Invalid SMILES: {e}") from e

def get_xyz_block(smiles: str) -> str:
    """Generates a 3D XYZ block for a molecule from its SMILES.
    Args:
        smiles (str): The SMILES representation of the molecule.
    Returns:
        str: XYZ block string representation of the molecule.
    """
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return ""
        mol = Chem.AddHs(mol)
        try:
            AllChem.EmbedMolecule(mol, randomSeed=42)  # type: ignore
        except Exception:
            return ""
        return Chem.MolToXYZBlock(mol)
    except Exception:
        return ""

def bde_valuate_controller(request: BDEEvaluateRequest) -> FragmentResponseData:
    """
    Controller para evaluar BDEs de enlaces específicos y generar fragmentos.
    Args:
        request (BDEEvaluateRequest): Contiene SMILES, molecule_id, bonds_idx y opciones de exportación.
    Returns:
        FragmentResponseData: Respuesta con enlaces predichos, fragmentos SMILES y/o XYZ según se solicite.
    """
    # Construir clave de caché
    bonds_key = ','.join(map(str, sorted(request.bonds_idx))) if request.bonds_idx else 'all_bonds'
    cache_key = f"evaluate_{request.smiles}_{request.molecule_id}_{bonds_key}_{request.export_smiles}_{request.export_xyz}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    
    # 1. Obtener información de la molécula
    all_info = get_all_info_molecule(request.smiles)
    mol = all_info.mol
    
    # 2. Verificar que el SMILES y molecule_id coincidan
    verify_smiles(all_info.smiles_canonical, request.molecule_id)
    
    # 3. Si bonds_idx es nulo o vacío, usar todos los índices de enlaces
    if not request.bonds_idx:
        bonds_to_process = list(range(mol.GetNumBonds()))
    else:
        bonds_to_process = request.bonds_idx
        # Validar que todos los índices de enlaces sean válidos
        for bond_idx in bonds_to_process:
            if bond_idx < 0 or bond_idx >= mol.GetNumBonds():
                raise ValueError(f"Bond index {bond_idx} is out of range for molecule with {mol.GetNumBonds()} bonds")
    
    # 4. Procesar TODOS los enlaces enviados y calcular BDEs
    bonds_predicted = []
    smiles_list = [] if request.export_smiles else None
    xyz_blocks = [] if request.export_xyz else None
    
    # Inicializar archivos de salida con el SMILES/XYZ original al inicio
    if request.export_smiles and smiles_list is not None:
        smiles_list.append(f"Molecule SMILES: {request.smiles}")
        smiles_list.append("#")  # Salto de línea 1
        smiles_list.append("=======================================================")  # Salto de línea 2
        smiles_list.append("#")  # Salto de línea 3
    
    if request.export_xyz and xyz_blocks is not None:
        xyz_blocks.append("Molecule XYZ:")
        xyz_blocks.append(get_xyz_block(request.smiles))
        xyz_blocks.append("#")  # Salto de línea 1
        xyz_blocks.append("========================================================")  # Salto de línea 2
        xyz_blocks.append("#")  # Salto de línea 3
    
    for bond_idx in bonds_to_process:
        bond = mol.GetBondWithIdx(bond_idx)
        begin_idx = bond.GetBeginAtomIdx()
        end_idx = bond.GetEndAtomIdx()
        atom1 = mol.GetAtomWithIdx(begin_idx)
        atom2 = mol.GetAtomWithIdx(end_idx)
        
        # Calcular BDE (get_bde_for_bond_indices ya retorna None si no es fragmentable)
        bde = get_bde_for_bond_indices(all_info, bond_idx) 

        # Crear objeto PredictedBond SIEMPRE (fragmentable o no)
        predicted_bond = PredictedBond(
            idx=bond_idx,
            bde=bde, 
            begin_atom_idx=begin_idx,
            end_atom_idx=end_idx,
            bond_atoms=f"{atom1.GetSymbol()}-{atom2.GetSymbol()}",
            bond_type=bond.GetBondType().name.lower(),
            is_fragmentable=(bde is not None)  # True si BDE fue calculado exitosamente
        )
        bonds_predicted.append(predicted_bond)
        
        # 5. Generar información de exportación para TODOS los enlaces
        if request.export_smiles and smiles_list is not None:
            if bde is not None:
                fragments = get_fragments_from_bond(mol, bond_idx)
                smiles_list.append(f"IDX: {bond_idx} | ATOMS: {begin_idx}-{end_idx} | BDE: {bde}")
                if len(fragments) >= 2:
                    smiles_list.append(f"F1:  {fragments[0]}")
                    smiles_list.append(f"F2:  {fragments[1]}")
                else:
                    smiles_list.append("F1:  [ERROR]")
                    smiles_list.append("F2:  [ERROR]")
            else:
                smiles_list.append(f"IDX: {bond_idx} | ATOMS: {begin_idx}-{end_idx} | BDE: Not fragmentable")
                smiles_list.append("F1:  No fragments generated")
                smiles_list.append("F2:  (bond is not single or is in ring)")
            smiles_list.append("##")  # Línea en blanco para separar entre enlaces
        
        if request.export_xyz and xyz_blocks is not None:
            if bde is not None:
                fragments = get_fragments_from_bond(mol, bond_idx)
                xyz_blocks.append(f"IDX: {bond_idx} | ATOMS: {begin_idx}-{end_idx} | BDE: {bde}")
                if len(fragments) >= 2:
                    xyz_blocks.append(f"F1:  {get_xyz_block(fragments[0])}")
                    xyz_blocks.append(f"F2:  {get_xyz_block(fragments[1])}")
                else:
                    xyz_blocks.append("F1:  [ERROR]")
                    xyz_blocks.append("F2:  [ERROR]")
            else:
                xyz_blocks.append(f"IDX: {bond_idx} | ATOMS: {begin_idx}-{end_idx} | BDE: Not fragmentable")
                xyz_blocks.append("F1:  No fragments generated")
                xyz_blocks.append("F2:  (bond is not single or is in ring)")
            xyz_blocks.append("##")  # Línea en blanco para separar entre enlaces
    xyz_block = "\n".join(xyz_blocks) if xyz_blocks is not None else None

    # Etiquetar en la imagen el mismo conjunto que se procesó:
    # - Si el request no trae índices -> todos
    # - Si trae índices -> solo esos
    bonds_to_label = bonds_to_process
    bde_map = {pb.idx: pb.bde for pb in bonds_predicted if pb.idx in set(bonds_to_label)}
    image_svg, canvas = generate_bde_svg_for_bonds(all_info.mol, bonds_to_label, bde_map)

    result = FragmentResponseData(
        smiles_canonical=all_info.smiles_canonical,
        molecule_id=all_info.molecule_id,
        bonds_predicted=bonds_predicted,
        smiles_list=smiles_list,
        xyz_block=xyz_block,
        image_svg=image_svg,
        canvas=canvas
    )
    # Guardar en caché
    cache_set(cache_key, result)
    return result
