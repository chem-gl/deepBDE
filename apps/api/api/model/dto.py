from typing import List, Optional, Dict, Any, Literal, TypeVar, Generic, Union
from enum import Enum
from pydantic import BaseModel, Field, field_validator, model_validator, ValidationError
# ---------- Enumeración de códigos de error ----------
class ErrorCode(str, Enum):
    """Enumeración de códigos de error estándar de la API."""
    SMILES_INVALID = "SMILES_INVALID"
    BOND_INDEX_OUT_OF_RANGE = "BOND_INDEX_OUT_OF_RANGE"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    MISSING_EXPORT_OPTION = "MISSING_EXPORT_OPTION"
# ---------- Clases comunes ----------

class ErrorDetail(BaseModel):
    """
    Detalle de error estándar para respuestas de la API.
    - code: Código de error único (ErrorCode).
    - message: Descripción amigable del error.
    """
    code: ErrorCode  # Código de error único, basado en la enumeración ErrorCode.
    message: str  # Descripción amigable del error.
class PredictedBond(BaseModel):
    """
    Detalle de un enlace químico y su BDE predicha.
    - idx: Índice del enlace en la molécula.
    - bde: Energía de disociación predicha para el enlace.
    - begin_atom_idx: Índice del átomo inicial del enlace.
    - end_atom_idx: Índice del átomo final del enlace.
    - bond_atoms: Representación legible del enlace (ejemplo: 'C-O').
    """
    idx: int  # Índice del enlace en la molécula.
    bde: Optional[float]  # Energía de disociación predicha para el enlace o None si no se pudo predecir por el tipo de enlace.
    begin_atom_idx: int  # Índice del átomo inicial del enlace.
    end_atom_idx: int  # Índice del átomo final del enlace.
    bond_atoms: str  # Representación legible del enlace (ejemplo: 'C-O').
    bond_type: Literal["single", "double", "triple", "aromatic"] = "single" 
    is_fragmentable: bool  # Indica si el enlace puede fragmentarse (enlace simple, etc.).


class Atom2D(BaseModel):
    """
    Información 2D de un átomo para visualización y metadatos.
    - x: Coordenada X
    - y: Coordenada Y
    - symbol: Símbolo químico del átomo (ej. 'C', 'O')
    - smiles: SMILES del átomo (opcional, para átomos complejos)
    """
    x: float
    y: float
    symbol: str
    smiles: Optional[str] = None
class Bond2D(BaseModel):
    """
    Información 2D de un enlace para visualización y metadatos.
    - start: Índice del átomo inicial
    - end: Índice del átomo final
    - start_coords: Coordenadas del átomo inicial
    - end_coords: Coordenadas del átomo final
    - bond_atoms: Representación legible del enlace (ej. 'C-O')
    """
    start: int
    end: int
    start_coords: Dict[str, float]
    end_coords: Dict[str, float]
    bond_atoms: str
    bond_type: Literal["single", "double", "triple", "aromatic"] = "single" 
# ---------- Plantilla de respuesta API ----------
T = TypeVar('T')
class APIResponse(BaseModel, Generic[T]):
    """
    Respuesta unificada para todos los endpoints.
    - status: 'success' o 'error'
    - data: Contenido de la respuesta
    - error: Detalle del error (opcional)
    """
    status: Literal["success", "error"] = "success"
    data: Optional[T] = None
    error: Optional[ErrorDetail] = None
# ---------- Modelos de endpoints ----------
# --- /predict/ ---
class MoleculeInfoRequest(BaseModel):
    """
    Entrada para /predict/.
    - smiles: SMILES de la molécula
    """
    smiles: str
class MoleculeInfoResponseData(BaseModel):
    """
    Salida de /predict/.
    - smiles_canonical: SMILES canónico con hidrógenos explícitos
    - image_svg: Imagen SVG enriquecida
    - canvas: Metadatos del lienzo
    - atoms: Diccionario de información 2D de átomos
    - bonds: Diccionario de información 2D de enlaces
    - molecule_id: ID único (hash SHA256)
    """
    smiles_canonical: str
    image_svg: str
    canvas: Dict[str, int]
    atoms: Dict[str, Atom2D]
    bonds: Dict[str, Bond2D]
    molecule_id: str
# --- /predict/single/ ---
class PredictSingleRequest(BaseModel):
    """
    Entrada para /predict/single/.
    - smiles: SMILES de la molécula
    - molecule_id: ID único de la molécula
    - bond_idx: Índice del enlace (>= 0)
    """
    smiles: str
    molecule_id: str
    bond_idx: int
    @field_validator('bond_idx')
    @classmethod
    def validate_bond_idx(cls, value):
        if value < 0:
            raise ValueError("El índice del enlace debe ser mayor o igual a 0")
        return value
class PredictSingleResponseData(BaseModel):
    """
    Salida de /predict/single/.
    - smiles_canonical: SMILES canónico
    - bond: Detalle del enlace predicho
    """
    smiles_canonical: str
    bond: PredictedBond
# --- /predict/multiple/ ---
class PredictMultipleRequest(BaseModel):
    """
    Entrada para /predict/multiple/.
    - molecule_id: ID de la molécula
    - bond_indices: Lista de índices de enlaces
    - smiles: (opcional)
    """
    smiles: str
    bond_indices: list[int]
    molecule_id: str
    @field_validator('bond_indices', mode='before')
    @classmethod
    def validate_bond_indices(cls, value):
        if not all(idx >= 0 for idx in value):
            raise ValueError("Todos los índices de enlace deben ser mayores o iguales a 0")
        return value
class PredictMultipleResponseData(BaseModel):
    """
    Salida de /predict/multiple/.
    - smiles: SMILES canónico
    - molecule_id: ID de la molécula
    - bonds: Lista de detalles de enlaces
    """
    smiles: str
    molecule_id: str
    bonds: List[PredictedBond]
    

class BDEEvaluateRequest(BaseModel):
    """
    Entrada para /fragment/.
    - smiles: SMILES con hidrógenos explícitos
    - molecule_id: ID de la molécula (opcional si se proporcionan fragmentos)
    - bonds_idx: Lista de índices de enlaces (opcional si se proporcionan fragmentos)
    - export_smiles: Indica si se debe exportar la lista de SMILES de los fragmentos
    - export_xyz: Indica si se debe exportar el bloque XYZ de los fragmentos
    """
    smiles: str
    molecule_id: str 
    bonds_idx: List[int] | None 
    export_smiles: bool = False
    export_xyz: bool = False
    @classmethod
    def validate(cls, value):
        if not value.get('fragments') and not value.get('molecule_id'):
            raise ValueError("should provide 'fragments' or 'molecule_id'")
        return value
class FragmentResponseData(BaseModel):
    """
    Salida de /fragment/.
    - smiles_canonical: SMILES canónico de la molécula original
    - molecule_id: ID de la molécula
    - bonds_predicted: Lista de enlaces predichos
    - smiles_list: Lista de SMILES de los fragmentos (opcional)
    - xyz_block: Bloque XYZ de los fragmentos (opcional)
    - image_svg: Imagen SVG con valores BDE
    - canvas: Información del lienzo
    """
    smiles_canonical: str
    molecule_id: str
    bonds_predicted: List[PredictedBond]
    smiles_list: Optional[List[str]] = None
    xyz_block: Optional[str] = None
    image_svg: str
    canvas: Dict[str, int]
    

# --- /predict/check/ ---
class PredictCheckRequest(BaseModel):
    """
    Entrada para /predict/check/.
    - smiles: SMILES original
    - bond_idx: Índice del enlace
    - products: Lista de SMILES esperados
    """
    smiles: str
    molecule_id: str
    bond_idx: int
    products: List[str] = Field(...)
class PredictCheckResponseData(BaseModel):
    """
    Salida de /predict/check/.
    - smiles_canonical: SMILES canónico
    - bond: Detalle del enlace analizado
    - products: Lista de SMILES resultantes
    """
    smiles_canonical: str
    bond: PredictedBond
    are_same_products: bool = False
    products: List[str]
# --- /predict/info-smile-canonical/ ---
class MoleculeSmileCanonicalRequest(BaseModel):
    """
    Salida de /predict/info-smile-canonical/.
    - smiles: smile 
    """
    smiles: str
class MoleculeSmileCanonicalResponseData(BaseModel):
    """
    Salida de /predict/info-smile-canonical/.
    - smiles_canonical: SMILES canónico con hidrógenos explícitos
    - molecule_id: ID único (hash SHA256)
    """
    smiles: str
    smiles_canonical: str
    molecule_id: str
# --- /infer/all/ ---
class InferAllRequest(BaseModel):
    """
    Entrada para /infer/all/.
    - smiles: SMILES de la molécula
    """
    smiles: str
class InferAllResponseData(BaseModel):
    """
    Salida de /infer/all/.
    - smiles_canonical: SMILES canónico
    - molecule_id: ID de la molécula
    - bonds: Lista de detalles de enlaces
    """
    smiles_canonical: str
    molecule_id: str
    bonds: List[PredictedBond]
# --- /download_report/ ---
class DownloadReportRequest(BaseModel):
    """
    Entrada para /download_report/.
    - smiles: SMILES de la molécula
    - format:  'txt'
    """
    smiles: str
    format: str
    @field_validator('format')
    @classmethod
    def _validate_format(cls, v: str) -> str:
        if v not in {"txt"}:
            raise ValueError("Formato no soportado: use 'txt'.")
        return v
class DownloadReportResponseData(BaseModel):
    """
    Salida de /download_report/.
    - report_base64: Reporte en base64
    """
    type: Literal["pdf", "txt"] = "pdf"
    report_base64: str
    
# --- /ObtainBDEFragments/ ---
class Fragments(BaseModel):
    """Fragmentos de la molécula."""
    Smile1: str
    Smile2: str
class ObtainBDEFragmentsRequest(BaseModel):
    """
    Entrada para /ObtainBDEFragments/.
    - smiles: SMILES de la molécula
    - fragments: Fragmentos de la molécula
    """
    smiles: str
    fragments: Fragments
    
class ObtainBDEFragmentsResponseData(BaseModel):
    """
    Salida de /ObtainBDEFragments/.
    - smiles_canonical: SMILES canónico de la molécula original
    - molecule_id: ID de la molécula
    - bonds_predicted: Lista de enlaces predichos
    - fragments: Fragmentos de la molécula
    """
    smiles_canonical: str
    molecule_id: str
    bonds_predicted: PredictedBond
    fragments: Fragments
    image_svg: str
    canvas: Dict[str, int]