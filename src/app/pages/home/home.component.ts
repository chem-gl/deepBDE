import { CommonModule } from '@angular/common';
import { Component, ElementRef, ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { RouterModule } from '@angular/router';
import { RDKitModule } from '@rdkit/rdkit';
import { saveAs } from 'file-saver';
import JSZip from 'jszip';
import { firstValueFrom } from 'rxjs';
import {
  BDEEvaluateRequest,
  FragmentResponseData,
  MoleculeInfoRequest,
  MoleculeInfoResponseData,
  V1Service,
} from '../../../../angular-client';
import { PredictedBond } from '../../../../angular-client/model/predictedBond';

// CSV BDE Override Types
type BondSource = 'DeepBDE' | 'CSB-QB3';
type PredictedBondWithSource = PredictedBond & { source?: BondSource };

interface CsvBondEntry {
  parent: string;      // SMILES canónico de la molécula padre
  frag1: string;       // SMILES del fragmento 1
  frag2: string;       // SMILES del fragmento 2
  bde: number;         // Valor BDE experimental
  bondType: string;    // Tipo de enlace (C-N, C-C, etc.)
}

export class ZoomPanState {
  public zoom = 1.0;
  public panX = 0;
  public panY = 0;
  public isPanning = false;
  public lastPanX = 0;
  public lastPanY = 0;
  public isFullscreen = false;
  constructor(initZoom = 1) {
    this.zoom = initZoom;
  }

  public updateZoom(factor: number) {
    this.zoom = Math.max(0.1, Math.min(15, this.zoom * factor));
  }
  public reset() {
    this.zoom = 1;
    this.panX = 0;
    this.panY = 0;
  }
  public startPan(event: MouseEvent) {
    this.isPanning = true;
    this.lastPanX = event.clientX;
    this.lastPanY = event.clientY;
  }
  public onPan(event: MouseEvent) {
    if (!this.isPanning) return;
    const deltaX = event.clientX - this.lastPanX;
    const deltaY = event.clientY - this.lastPanY;
    this.panX += deltaX / this.zoom;
    this.panY += deltaY / this.zoom;
    this.lastPanX = event.clientX;
    this.lastPanY = event.clientY;
  }
  public endPan() {
    this.isPanning = false;
  }
  public getTransform(): string {
    return `scale(${this.zoom}) translate(${this.panX}px, ${this.panY}px)`;
  }
}
function sanitizeSvg(svg: string, sanitizer: DomSanitizer): SafeHtml {
  if (!svg) return '';
  let cleanSvg = svg.trim();
  cleanSvg = cleanSvg.replace(/encoding='iso-8859-1'/g, "encoding='UTF-8'");
  cleanSvg = cleanSvg.replace(/xmlns=/g, ' xmlns=');
  cleanSvg = cleanSvg.replace(/xmlns:rdkit=/g, ' xmlns:rdkit=');
  cleanSvg = cleanSvg.replace(/xmlns:xlink=/g, ' xmlns:xlink=');
  cleanSvg = cleanSvg.replace(/xml:space=/g, ' xml:space=');
  cleanSvg = cleanSvg.replace(/width="[^"]*"/, 'width="100%"');
  cleanSvg = cleanSvg.replace(/height="[^"]*"/, 'height="auto"');
  if (!/width="[^"]*"/.test(cleanSvg)) {
    cleanSvg = cleanSvg.replace('<svg', '<svg width="100%"');
  }
  if (!/height="[^"]*"/.test(cleanSvg)) {
    cleanSvg = cleanSvg.replace('<svg', '<svg height="auto"');
  }
  cleanSvg = cleanSvg.replace(/viewBox=/g, ' viewBox=');
  cleanSvg = cleanSvg.replace(/\s+/g, ' ');
  cleanSvg = cleanSvg.replace(
    /^<\?xml[^>]+\?><svg/,
    "<?xml version='1.0' encoding='UTF-8'?>\n<svg"
  );
  return sanitizer.bypassSecurityTrustHtml(cleanSvg);
}
function isValidSmiles(smiles: string, RDKit?: RDKitModule): boolean | null {
  if (!smiles || smiles.trim() === '' || smiles.includes('.')) return false;
  if (!RDKit) return null;
  try {
    const mol = RDKit.get_mol(smiles);
    return !!mol && mol.is_valid();
  } catch {
    return false;
  }
}
function createZoomPanState(initZoom = 1): ZoomPanState {
  return new ZoomPanState(initZoom);
}
function setupKetcher(ketcherFrame: ElementRef<HTMLIFrameElement>): void {
  if (ketcherFrame && ketcherFrame.nativeElement) {
    const iframe = ketcherFrame.nativeElement;
    if (!iframe.src.endsWith('ketcher/index.html')) {
      iframe.src = 'ketcher/index.html';
    }
  }
}
export interface ExtendedFragmentResponseData extends FragmentResponseData {
  zoomPan?: ZoomPanState;
  smiles?: string;
  sanitizedSvg?: SafeHtml;
}
class Molecule {
  public smiles: string;
  public idSmile: string;
  public canonical: string;
  constructor(smiles: string, idSmile: string, canonical: string) {
    this.smiles = smiles;
    this.idSmile = idSmile;
    this.canonical = canonical;
  }
}
@Component({
  selector: 'app-home',
  standalone: true,
  imports: [CommonModule, RouterModule, FormsModule],
  templateUrl: './home.component.html',
  styleUrls: ['./home.component.scss'],
})
export class HomeComponent {
  // In-memory caches for API results
  private canonicalSmilesCache = new Map<string, any>();
  private bdeResultsCache = new Map<string, any>();

  // CSV BDE Override infrastructure
  private csvIndex = new Map<string, CsvBondEntry[]>();
  private smilesCanonicalCache = new Map<string, string>();
  private csvLoadPromise: Promise<void> | null = null;
  private csvLoaded = false;
  private processingCsvOverrides = false;
  private _filteredBondsCache: PredictedBondWithSource[] | null = null;

  private async getCanonicalSmiles(smiles: string): Promise<any> {
    if (this.canonicalSmilesCache.has(smiles)) {
      return this.canonicalSmilesCache.get(smiles);
    }
    const response = await firstValueFrom(
      this.v1Service.v1PredictInfoSmileCanonicalCreate({ smiles }),
    );
    this.canonicalSmilesCache.set(smiles, response);
    return response;
  }

  private async getBdeResults(
    smiles: string,
    molecule_id: string,
  ): Promise<any> {
    const key = `${smiles}|${molecule_id}`;
    if (this.bdeResultsCache.has(key)) {
      return this.bdeResultsCache.get(key);
    }
    const response = await firstValueFrom(
      this.v1Service.v1BDEEvaluateCreate({
        smiles,
        molecule_id,
        export_smiles: true,
        export_xyz: true,
        bonds_idx: [],
      }),
    );
    this.bdeResultsCache.set(key, response);
    return response;
  }

  // CSV BDE Override Methods
  private async ensureCsvLoaded(): Promise<void> {
    if (this.csvLoaded) return;
    if (this.csvLoadPromise) return this.csvLoadPromise;

    this.csvLoadPromise = (async () => {
      try {
        const response = await fetch(
          '/authors/combined_dataset-14Dec2024_canonical.csv',
        );
        if (!response.ok) {
          console.error('[CSV] Failed to load CSV file:', response.statusText);
          return;
        }
        const csvText = await response.text();
        const lines = csvText.split('\n').filter((line) => line.trim());
        console.log('[CSV] Lines to parse:', lines.length);

        // Skip header (first line)
        for (let i = 1; i < lines.length; i++) {
          const parts = lines[i].split(',');
          if (parts.length < 6) continue;

          const [serial, parent, frag1, frag2, bdeStr, bondType] = parts;
          const bde = parseFloat(bdeStr);

          if (Number.isNaN(bde)) continue;

          // CSV parent SMILES are already canonical, no need to canonicalize again
          const entry: CsvBondEntry = {
            parent: parent.trim(),
            frag1: frag1.trim(),
            frag2: frag2.trim(),
            bde,
            bondType: bondType.trim(),
          };

          if (!this.csvIndex.has(entry.parent)) {
            this.csvIndex.set(entry.parent, []);
          }
          this.csvIndex.get(entry.parent)!.push(entry);
        }

        console.log('[CSV] Indexed parents:', this.csvIndex.size);
        this.csvLoaded = true;
      } catch (error) {
        console.error('[CSV] Error loading CSV:', error);
      }
    })();

    return this.csvLoadPromise;
  }

  private canonicalizeSmilesCached(smiles: string): string {
    if (this.smilesCanonicalCache.has(smiles)) {
      return this.smilesCanonicalCache.get(smiles)!;
    }

    if (!this.RDKit) return smiles;

    try {
      const mol = this.RDKit.get_mol(smiles);
      if (mol && mol.is_valid()) {
        const canonical = mol.get_smiles();
        this.smilesCanonicalCache.set(smiles, canonical);
        return canonical;
      }
    } catch (error) {
      // Ignore errors, return original
    }

    this.smilesCanonicalCache.set(smiles, smiles);
    return smiles;
  }

  private extractFragmentSmiles(line: string): string | null {
    if (!line || line.trim() === '') return null;

    // Expected format: "F1:  [SMILES]" or "F2:  [SMILES]"
    if (!line.startsWith('F1:') && !line.startsWith('F2:')) return null;

    const smiles = line.substring(4).trim();

    // Filter out error cases (but allow [H] as it's a valid radical)
    if (
      smiles.includes('No fragments') ||
      smiles.includes('Error') ||
      smiles === ''
    ) {
      return null;
    }

    return smiles;
  }

  private applyCsvToBondWithFragments(
    parentSmiles: string,
    bond: PredictedBond,
    frag1: string,
    frag2: string,
  ): PredictedBondWithSource {
    console.log(`[BDE FLOW] >>>>> applyCsvToBondWithFragments called <<<<<`);
    console.log(
      `[BDE FLOW] Parent SMILES for lookup (original): "${parentSmiles}"`,
    );

    // Canonicalize parent SMILES to match CSV index (removes explicit H)
    const parentCanonical = this.canonicalizeSmilesCached(parentSmiles);
    console.log(
      `[BDE FLOW] Parent SMILES for lookup (canonical): "${parentCanonical}"`,
    );
    console.log(`[BDE FLOW] Fragment 1 (input): "${frag1}"`);
    console.log(`[BDE FLOW] Fragment 2 (input): "${frag2}"`);
    console.log(`[BDE FLOW] Current bond BDE (from ML): ${bond.bde}`);
    console.log(`[BDE FLOW] Current bond atoms: ${bond.bond_atoms}`);
    console.log(`[BDE FLOW] Checking if parent SMILES exists in CSV index...`);
    console.log(
      `[BDE FLOW] csvIndex.has("${parentCanonical}") = ${this.csvIndex.has(parentCanonical)}`,
    );

    const entries = this.csvIndex.get(parentCanonical);
    if (!entries) {
      console.log(
        `[BDE FLOW] ❌ No CSV entries found for parent SMILES: "${parentCanonical}"`,
      );
      console.log(`[BDE FLOW] Bond will keep ML predicted BDE: ${bond.bde}`);
      return { ...bond, source: 'DeepBDE' as BondSource };
    }

    console.log(
      `[BDE FLOW] ✓ Found ${entries.length} CSV entries for this parent SMILES`,
    );

    // Canonicalize fragments for comparison
    console.log('[BDE FLOW] Canonicalizing fragments...');
    const f1Canonical = this.canonicalizeSmilesCached(frag1);
    const f2Canonical = this.canonicalizeSmilesCached(frag2);
    console.log(`[BDE FLOW] Fragment 1 canonical: "${f1Canonical}"`);
    console.log(`[BDE FLOW] Fragment 2 canonical: "${f2Canonical}"`);

    console.log('[BDE FLOW] Searching for fragment match in CSV entries...');
    const match = entries.find((entry, idx) => {
      const csvF1 = this.canonicalizeSmilesCached(entry.frag1);
      const csvF2 = this.canonicalizeSmilesCached(entry.frag2);

      console.log(
        `[BDE FLOW] Checking CSV entry ${idx + 1}/${entries.length}:`,
      );
      console.log(`[BDE FLOW]   CSV frag1: "${csvF1}"`);
      console.log(`[BDE FLOW]   CSV frag2: "${csvF2}"`);
      console.log(`[BDE FLOW]   CSV BDE: ${entry.bde}`);

      const match1 = f1Canonical === csvF1 && f2Canonical === csvF2;
      const match2 = f1Canonical === csvF2 && f2Canonical === csvF1;

      console.log(`[BDE FLOW]   Match (f1==csvF1 && f2==csvF2): ${match1}`);
      console.log(`[BDE FLOW]   Match (f1==csvF2 && f2==csvF1): ${match2}`);

      return match1 || match2;
    });

    if (match) {
      console.log(
        `[BDE FLOW] ✓✓✓ MATCH FOUND! Using CSV BDE=${match.bde} instead of ML BDE=${bond.bde}`,
      );
      return { ...bond, bde: match.bde, source: 'CSB-QB3' as BondSource };
    }

    console.log(
      `[BDE FLOW] ❌ No matching fragments found in ${entries.length} CSV entries`,
    );
    return { ...bond, source: 'DeepBDE' as BondSource };
  }

  private async applyCsvOverridesWithFragments(
    parentSmiles: string,
    bonds: PredictedBond[],
    smilesList: string[],
  ): Promise<PredictedBondWithSource[]> {
    await this.ensureCsvLoaded();

    if (!this.csvLoaded) {
      console.log('[BDE FLOW] ===== CSV not loaded, skipping overrides =====');
      return bonds.map((b) => ({ ...b, source: 'DeepBDE' as BondSource }));
    }

    console.log('[BDE FLOW] ===== applyCsvOverridesWithFragments called =====');
    console.log('[BDE FLOW] Parent SMILES (canonical from API):', parentSmiles);
    console.log('[BDE FLOW] Number of bonds to process:', bonds.length);
    console.log('[BDE FLOW] smiles_list total lines:', smilesList.length);
    console.log(
      '[BDE FLOW] CSV index size:',
      this.csvIndex.size,
      'parent molecules',
    );
    console.log(
      '[BDE FLOW] First 20 lines of smiles_list:',
      smilesList.slice(0, 20),
    );

    const bondsWithSource: PredictedBondWithSource[] = [];

    for (let idx = 0; idx < bonds.length; idx++) {
      const bond = bonds[idx];

      console.log(`[BDE FLOW] --- Processing bond index ${idx} ---`);
      console.log(`[BDE FLOW] Bond atoms: ${bond.bond_atoms}`);
      console.log(`[BDE FLOW] Bond is_fragmentable: ${bond.is_fragmentable}`);

      if (!bond.is_fragmentable) {
        bondsWithSource.push({ ...bond, source: 'DeepBDE' as BondSource });
        console.log(
          `[BDE FLOW] ❌ Bond ${idx}: Not fragmentable, keeping ML BDE`,
        );
        continue;
      }

      // Calculate indices in smiles_list
      // Structure: 4 header lines + 4 lines per bond
      const baseIdx = 4 + idx * 4;

      if (baseIdx + 2 >= smilesList.length) {
        bondsWithSource.push({ ...bond, source: 'DeepBDE' as BondSource });
        console.log(
          `[BDE FLOW] ❌ Bond ${idx}: smiles_list too short (baseIdx=${baseIdx}, length=${smilesList.length})`,
        );
        continue;
      }

      const f1Line = smilesList[baseIdx + 1];
      const f2Line = smilesList[baseIdx + 2];

      console.log(`[BDE FLOW] Bond ${idx}: baseIdx=${baseIdx}`);
      console.log(`[BDE FLOW]   f1Line=[${baseIdx + 1}]: "${f1Line}"`);
      console.log(`[BDE FLOW]   f2Line=[${baseIdx + 2}]: "${f2Line}"`);

      const frag1 = this.extractFragmentSmiles(f1Line);
      const frag2 = this.extractFragmentSmiles(f2Line);

      if (!frag1 || !frag2) {
        bondsWithSource.push({ ...bond, source: 'DeepBDE' as BondSource });
        console.log(
          `[BDE FLOW] ❌ Bond ${idx}: Could not extract fragments from lines`,
        );
        continue;
      }

      console.log(
        `[BDE FLOW] Extracted fragments: frag1="${frag1}", frag2="${frag2}"`,
      );

      const bondWithSource = this.applyCsvToBondWithFragments(
        parentSmiles,
        bond,
        frag1,
        frag2,
      );

      const frag1Can = this.canonicalizeSmilesCached(frag1);
      const frag2Can = this.canonicalizeSmilesCached(frag2);
      console.log(
        `[BDE FLOW] Bond ${idx} canonical fragments: f1="${frag1Can}", f2="${frag2Can}"`,
      );

      if (bondWithSource.source === 'CSB-QB3') {
        console.log(
          `[BDE FLOW] ✅ Bond ${idx}: REPLACED DeepBDE=${bond.bde} WITH CSV BDE=${bondWithSource.bde}`,
        );
      } else {
        console.log(
          `[BDE FLOW] ❌ Bond ${idx}: No CSV match, keeping ML BDE=${bond.bde}`,
        );
      }

      bondsWithSource.push(bondWithSource);
    }

    console.log('[BDE FLOW] ===== Finished processing all bonds =====');
    const csvBondsCount = bondsWithSource.filter(
      (b) => b.source === 'CSB-QB3',
    ).length;
    console.log(
      `[BDE FLOW] Total bonds with CSV overrides: ${csvBondsCount} / ${bonds.length}`,
    );
    bondsWithSource.forEach((bond, idx) => {
      if (bond.source === 'CSB-QB3') {
        console.log(
          `[BDE FLOW] Final Bond ${idx}: BDE=${bond.bde} from CSV (bond_atoms=${bond.bond_atoms})`,
        );
      }
    });

    return bondsWithSource;
  }

  public previewModalOpen = false;
  public previewSvg: SafeHtml | null = null;
  public zoomPanMain = createZoomPanState(1.7);
  public zoomPanBde = createZoomPanState(1.7);
  public bdeResultsSanitizedSvg: SafeHtml | null = null;
  public selectedMode: 'smiles' | 'fragments' | 'smilesList' = 'smiles';
  public smilesList: Array<{ smiles: string; valid: boolean | null }> = [];
  public smilesListInput: string = '';
  public smilesInput = '';
  public loadingInfo = false;
  public error: string | null = null;
  public svgImage: string | null = null;
  public sanitizedSvg: SafeHtml | null = null;
  public isFullscreen = false;
  public selectAllBonds = true;
  public customBondsInput = '';
  public includeXyzFormat = false;
  public includeSmilesFormat = false;
  public moleculeInfo?: MoleculeInfoResponseData;
  public bdeResults?: FragmentResponseData;
  public allBDEResults: ExtendedFragmentResponseData[] = [];
  private moleculeList: Molecule[] = [];
  public loadingBDE = false;
  public smiles = '';
  private RDKit?: RDKitModule;
  public rdkitReady = false;
  @ViewChild('ketcherFrame')
  public ketcherFrame!: ElementRef<HTMLIFrameElement>;
  public addSmilesToList(): void {
    const value = this.smilesListInput.trim();
    if (!value) return;
    if (this.smilesList.some((item) => item.smiles === value)) return;
    this.smilesList.push({
      smiles: value,
      valid: isValidSmiles(value, this.RDKit),
    });
    this.smilesListInput = '';
  }
  public removeSmilesFromList(item: {
    smiles: string;
    valid: boolean | null;
  }): void {
    this.smilesList = this.smilesList.filter((s) => s !== item);
  }
  public onSmilesFileUpload(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (!input.files || input.files.length === 0) return;
    this.loadSmilesFromFile(input.files[0]);
  }
  private loadSmilesFromFile(file: File): void {
    const reader = new FileReader();
    reader.onload = () => {
      const text = reader.result as string;
      const lines = text
        .split(/\r?\n/)
        .map((l) => l.trim())
        .filter((l) => l);
      for (const line of lines) {
        if (!this.smilesList.some((item) => item.smiles === line)) {
          this.smilesList.push({
            smiles: line,
            valid: isValidSmiles(line, this.RDKit),
          });
        }
      }
    };
    reader.readAsText(file);
  }
  public async analyzeSmilesList(): Promise<void> {
    const validSmiles = this.smilesList
      .filter((s) => s.valid)
      .map((s) => s.smiles);
    if (validSmiles.length === 0) {
      this.error = 'No valid SMILES in the list.';
      return;
    }
    this.allBDEResults = [];
    this.moleculeList = [];
    this.loadingBDE = true;
    let hadAnyError = false;
    try {
      for (const smiles of validSmiles) {
        let response: any;
        try {
          response = await this.getCanonicalSmiles(smiles);
        } catch (err) {
          hadAnyError = true;
          console.error('Error getting canonical SMILES for', smiles, err);
          continue;
        }
        if (!response?.data) {
          hadAnyError = true;
          console.warn('Empty response for SMILES:', smiles);
          continue;
        }

        this.moleculeList.push(
          new Molecule(
            response.data.smiles,
            response.data.molecule_id,
            response.data.smiles_canonical,
          ),
        );

        let bdeResponse: any;
        try {
          bdeResponse = await this.getBdeResults(
            response.data.smiles,
            response.data.molecule_id,
          );
        } catch (err) {
          hadAnyError = true;
          console.error('Error getting BDE data for', smiles, err);
          continue;
        }
        if (!bdeResponse?.data) {
          hadAnyError = true;
          console.warn('Empty BDE response for SMILES:', smiles);
          continue;
        }

        this.allBDEResults.push({
          ...bdeResponse.data,
          smiles: response.data.smiles,
          zoomPan: new ZoomPanState(1),
          sanitizedSvg: sanitizeSvg(bdeResponse.data.image_svg, this.sanitizer),
        });
      }
      if (hadAnyError) {
        this.error =
          'Some SMILES could not be processed. Check the console for details.';
      } else {
        this.error = null;
      }
    } catch (err) {
      console.error('Unexpected error in analyzeSmilesList:', err);
      this.error =
        'An unexpected error occurred while analyzing the SMILES list.';
    } finally {
      this.loadingBDE = false;
    }
  }
  public constructor(
    private readonly v1Service: V1Service,
    private readonly sanitizer: DomSanitizer,
  ) {
    document.addEventListener('keydown', (event) => {
      if (
        event.key === 'Escape' &&
        (this.zoomPanMain.isFullscreen || this.zoomPanBde.isFullscreen)
      ) {
        this.zoomPanMain.reset();
        this.zoomPanBde.reset();
        this.zoomPanMain.isFullscreen = false;
        this.zoomPanBde.isFullscreen = false;
      }
    });
  }
  private async initRdkit(): Promise<void> {
    try {
      if ((window as any).initRDKitModule) {
        this.RDKit = await (window as any).initRDKitModule({
          locateFile: (file: string) => `/assets/rdkit/${file}`,
        });
        (window as any).RDKit = this.RDKit;
        this.rdkitReady = true;
      } else {
        console.warn(
          'initRDKitModule no encontrado en window. Revisa que RDKit_minimal.js esté cargado.',
        );
      }
    } catch (err) {
      console.error('Error inicializando RDKit:', err);
    }
  }
  public smilesHistory: string[] = [];
  public ngOnInit(): void {
    const saved = localStorage.getItem('smilesHistory');
    if (saved) {
      try {
        this.smilesHistory = JSON.parse(saved);
      } catch {}
    }
    this.initRdkit();
    this.allBDEResults.forEach((result) => {
      result.zoomPan = createZoomPanState(1);
    });
  }
  public async openSmilesPreview(item: {
    smiles: string;
    valid: boolean | null;
  }) {
    if (!this.RDKit || !item.valid) return;
    try {
      const mol = this.RDKit.get_mol(item.smiles);
      if (mol && mol.is_valid()) {
        let svg = mol.get_svg(350, 200).trim();
        this.previewSvg = sanitizeSvg(svg, this.sanitizer);
        this.previewModalOpen = true;
      } else {
        this.previewSvg = sanitizeSvg(
          '<div style="color:red;">Invalid molecule</div>',
          this.sanitizer,
        );
        this.previewModalOpen = true;
      }
    } catch {
      this.previewSvg = sanitizeSvg(
        '<div style="color:red;">Error generating preview</div>',
        this.sanitizer,
      );
      this.previewModalOpen = true;
    }
  }
  public closePreviewModal(): void {
    this.previewModalOpen = false;
    this.previewSvg = null;
  }
  public trackSmiles(
    index: number,
    item: { smiles: string; valid: boolean | null },
  ) {
    return item.smiles;
  }
  public getValidSmilesCount(): number {
    return this.smilesList.filter((s) => s.valid === true).length;
  }
  public hasValidSmiles(): boolean {
    return this.smilesList.some((s) => s.valid === true);
  }
  public zoomInMain(): void {
    this.zoomPanMain.updateZoom(1.2);
  }
  public zoomOutMain(): void {
    this.zoomPanMain.updateZoom(1 / 1.2);
  }
  public resetZoomMain(): void {
    this.zoomPanMain.reset();
  }
  public toggleFullscreenMain(): void {
    this.zoomPanMain.isFullscreen = !this.zoomPanMain.isFullscreen;
    if (!this.zoomPanMain.isFullscreen) this.zoomPanMain.reset();
  }
  public getTransformMain(): string {
    return this.zoomPanMain.getTransform();
  }
  public startPanMain(event: MouseEvent): void {
    this.zoomPanMain.startPan(event);
    event.preventDefault();
  }
  public onPanMain(event: MouseEvent): void {
    this.zoomPanMain.onPan(event);
  }
  public endPanMain(): void {
    this.zoomPanMain.endPan();
  }
  public onWheelMain(event: WheelEvent): void {
    event.preventDefault();
    const delta = event.deltaY > 0 ? 0.9 : 1.1;
    this.zoomPanMain.updateZoom(delta);
  }
  public zoomInBde(): void {
    this.zoomPanBde.updateZoom(1.2);
  }
  public zoomOutBde(): void {
    this.zoomPanBde.updateZoom(1 / 1.2);
  }
  public resetZoomBde(): void {
    this.zoomPanBde.reset();
  }
  public toggleFullscreenBde(): void {
    this.zoomPanBde.isFullscreen = !this.zoomPanBde.isFullscreen;
    if (!this.zoomPanBde.isFullscreen) this.zoomPanBde.reset();
  }
  public getTransformBde(): string {
    return this.zoomPanBde.getTransform();
  }
  public startPanBde(event: MouseEvent): void {
    this.zoomPanBde.startPan(event);
    event.preventDefault();
  }
  public onPanBde(event: MouseEvent): void {
    this.zoomPanBde.onPan(event);
  }
  public endPanBde(): void {
    this.zoomPanBde.endPan();
  }
  public onWheelBde(event: WheelEvent): void {
    event.preventDefault();
    const delta = event.deltaY > 0 ? 0.9 : 1.1;
    this.zoomPanBde.updateZoom(delta);
  }
  public saveSmilesHistory(): void {
    localStorage.setItem('smilesHistory', JSON.stringify(this.smilesHistory));
  }
  public ngAfterViewInit(): void {
    if (this.selectedMode === 'fragments') {
      this.setupKetcherIfAvailable();
    }
  }
  private setupKetcherIfAvailable(): void {
    setupKetcher(this.ketcherFrame);
  }
  public async getSmiles(): Promise<void> {
    this.error = null;
    if (!this.ketcherFrame?.nativeElement) {
      this.error =
        'Molecular editor is not available. Please switch to Draw Molecule mode.';
      return;
    }

    const iframeWin = this.ketcherFrame.nativeElement.contentWindow;
    if (!iframeWin) {
      this.error = 'Cannot access molecular editor. Please refresh the page.';
      return;
    }
    const ketcher = (iframeWin as any).ketcher;
    if (ketcher && typeof ketcher.getSmiles === 'function') {
      try {
        const smilesResult = await ketcher.getSmiles();
        this.handleSmilesResult(smilesResult);
      } catch (error) {
        this.error =
          'Error getting SMILES from molecular editor. Trying alternative method...';
        this.getSmilesViaPostMessage();
      }
    } else {
      this.getSmilesViaPostMessage();
    }
  }
  private handleSmilesResult(smilesResult: string): void {
    if (!smilesResult || smilesResult.trim() === '') {
      this.error = 'No molecule drawn. Please draw a molecule first.';
      return;
    }
    if (!isValidSmiles(smilesResult, this.RDKit)) {
      this.error = 'Invalid SMILES.';
      return;
    }
    this.smiles = smilesResult;
    this.smilesInput = this.smiles;
  }
  private getSmilesViaPostMessage(): void {
    if (!this.ketcherFrame?.nativeElement) return;
    const iframeWin = this.ketcherFrame.nativeElement.contentWindow;
    if (!iframeWin) return;
    const messageId = Math.random().toString(36).substr(2, 9);
    const messageHandler = (event: MessageEvent) => {
      if (event.data && event.data.id === messageId) {
        if (event.data.type === 'result') {
          this.handleSmilesResult(event.data.payload);
        } else if (event.data.type === 'error') {
          this.error =
            'Error getting SMILES from molecular editor: ' + event.data.payload;
        }
        window.removeEventListener('message', messageHandler);
      }
    };
    window.addEventListener('message', messageHandler);
    iframeWin.postMessage(
      {
        id: messageId,
        type: 'request',
        method: 'getSmiles',
        params: {},
      },
      '*',
    );
  }
  public analyzeMoleculeFromDrawing(): void {
    if (!this.smiles.trim()) {
      this.error = 'Please draw a molecule and get SMILES first';
      return;
    }
    if (!isValidSmiles(this.smiles.trim(), this.RDKit)) {
      this.error = 'Invalid SMILES.';
      return;
    }
    this.smilesInput = this.smiles;
    this.getMoleculeData();
  }
  public async copySmilesToClipboard(): Promise<void> {
    if (!this.smiles) {
      this.error = 'No hay SMILES para copiar.';
      return;
    }
    try {
      await navigator.clipboard.writeText(this.smiles);
      this.error = null;
    } catch (error) {
      this.error = 'Error al copiar SMILES al portapapeles.';
      console.error('Failed to copy SMILES to clipboard:', error);
    }
  }
  public reloadKetcher(): void {
    if (this.ketcherFrame && this.ketcherFrame.nativeElement) {
      this.smiles = '';
      this.error = null;
      if (!this.ketcherFrame.nativeElement.src.endsWith('ketcher/index.html')) {
        this.ketcherFrame.nativeElement.src = 'ketcher/index.html';
      } else {
        this.ketcherFrame.nativeElement.src = '';
        setTimeout(() => {
          this.ketcherFrame.nativeElement.src = 'ketcher/index.html';
        }, 100);
      }
    }
  }
  public setMode(mode: 'smiles' | 'fragments' | 'smilesList'): void {
    this.selectedMode = mode;
    this.clearAllOutputs();
    if (mode === 'fragments') {
      setTimeout(() => {
        this.setupKetcherIfAvailable();
      }, 100);
    }
    if (mode === 'smilesList') {
      this.smilesList = [];
      this.allBDEResults = [];
      this.loadingBDE = false;
      this.smilesListInput = '';
    }
  }
  private clearAllOutputs(): void {
    this.smilesInput = '';
    this.smiles = '';
    this.svgImage = null;
    this.sanitizedSvg = null;
    this.error = null;
    this.bdeResults = undefined;
    this.moleculeInfo = undefined;
    this.loadingInfo = false;
    this.selectAllBonds = true;
    this.customBondsInput = '';
    this.includeXyzFormat = false;
    this.includeSmilesFormat = false;
    this.zoomPanMain = createZoomPanState(1.7);
    this.zoomPanBde = createZoomPanState(1.7);
    this.showResults = false;
    this.previewModalOpen = false;
    this.previewSvg = null;
  }
  public clearResults(): void {
    this.svgImage = null;
    this.sanitizedSvg = null;
    this.error = null;
    this.bdeResults = undefined;
  }
  public onSelectAllBondsChange(): void {
    if (this.selectAllBonds) {
      this.customBondsInput = '';
    }
    setTimeout(() => {
      const bondsInput = document.getElementById('custom-bonds');
      if (bondsInput) {
        bondsInput.focus();
      }
    }, 0);
  }
  public getBDE(): void {
    if (!this.includeXyzFormat && !this.includeSmilesFormat) {
      console.error('No output format selected - will use default behavior');
    }
    if (!this.moleculeInfo) {
      this.error = 'Molecule information is required to get BDE';
      return;
    }
    let bonds: Array<number> | null = null;
    if (!this.selectAllBonds && this.customBondsInput.trim()) {
      bonds = this.parseBondIndices(this.customBondsInput.trim());
      if (bonds.length === 0) {
        this.error =
          'Invalid bond indices format. Use numbers separated by commas and ranges with dashes (e.g., 1,2,5-8,10)';
        return;
      }
      const maxBonds: number = Object.keys(this.moleculeInfo.bonds).length;
      if (bonds.some((b) => b < 0 || b >= maxBonds)) {
        this.error = `Bond indices must be between 0 and ${maxBonds - 1}`;
        return;
      }
    }
    this.loadingBDE = true;
    this.error = null;
    const request: BDEEvaluateRequest = {
      smiles: this.moleculeInfo.smiles_canonical,
      molecule_id: this.moleculeInfo.molecule_id,
      export_smiles: true, // Always true to enable CSV fragment matching
      export_xyz: this.includeXyzFormat,
      bonds_idx: bonds,
    };
    console.log('[BDE FLOW] ===== Starting BDE calculation =====');
    console.log(
      '[BDE FLOW] Molecule SMILES:',
      this.moleculeInfo.smiles_canonical,
    );
    console.log('[BDE FLOW] Molecule ID:', this.moleculeInfo.molecule_id);
    console.log(
      '[BDE FLOW] Bond indices:',
      bonds && bonds.length > 0 ? bonds : 'all bonds',
    );
    console.log('[BDE FLOW] Request params:', request);
    this.v1Service.v1BDEEvaluateCreate(request).subscribe({
      next: async (response) => {
        this.loadingBDE = false;
        console.log('[BDE FLOW] ===== API Response received =====');
        console.log('[BDE FLOW] Response object:', response);
        if (!response) {
          this.error = 'No data received from the server';
          return;
        }
        if (response.data) {
          console.log(
            '[BDE FLOW] Response data.smiles_canonical:',
            response.data.smiles_canonical,
          );
          console.log(
            '[BDE FLOW] Response data.bonds_predicted count:',
            response.data.bonds_predicted?.length || 0,
          );
          console.log(
            '[BDE FLOW] Response data.smiles_list count:',
            response.data.smiles_list?.length || 0,
          );
          // Apply CSV overrides if we have fragments (only once)
          if (
            !this.processingCsvOverrides &&
            response.data.bonds_predicted &&
            response.data.smiles_list &&
            response.data.smiles_canonical
          ) {
            this.processingCsvOverrides = true;
            console.log(
              '[BDE FLOW] ===== Starting CSV override processing =====',
            );
            const bondsWithCsvOverrides =
              await this.applyCsvOverridesWithFragments(
                response.data.smiles_canonical,
                response.data.bonds_predicted,
                response.data.smiles_list,
              );
            this.bdeResults = {
              ...response.data,
              bonds_predicted: bondsWithCsvOverrides,
            };
            this._filteredBondsCache = null; // Invalidate cache
            this.processingCsvOverrides = false;
            console.log(
              '[DEBUG] bdeResults assigned with',
              bondsWithCsvOverrides.length,
              'bonds',
            );
            bondsWithCsvOverrides.slice(0, 5).forEach((bond, idx) => {
              console.log(
                `[DEBUG] Bond ${idx}: BDE=${bond.bde}, source=${bond.source}, bond_atoms=${bond.bond_atoms}`,
              );
            });
          } else {
            this.bdeResults = response.data;
            this._filteredBondsCache = null; // Invalidate cache
          }
          this.error = null;
          if (this.bdeResults.image_svg) {
            this.bdeResultsSanitizedSvg = sanitizeSvg(
              this.bdeResults.image_svg,
              this.sanitizer,
            );
          } else {
            this.bdeResultsSanitizedSvg = null;
          }
        } else {
          this.error = 'No BDE data found in the response';
        }
      },
      error: (error: any) => {
        this.loadingBDE = false;
        this.error =
          'Error getting BDE information: ' +
          (error.message || 'Unknown error');
      },
    });
  }
  private parseBondIndices(input: string): number[] {
    const indices: number[] = [];
    try {
      const parts = input.split(',');
      for (const part of parts) {
        const trimmedPart = part.trim();
        if (trimmedPart.includes('-')) {
          const rangeParts = trimmedPart.split('-');
          if (rangeParts.length === 2) {
            const start = parseInt(rangeParts[0].trim(), 10);
            const end = parseInt(rangeParts[1].trim(), 10);
            if (!isNaN(start) && !isNaN(end) && start <= end) {
              for (let i = start; i <= end; i++) {
                indices.push(i);
              }
            }
          }
        } else {
          const num = parseInt(trimmedPart, 10);
          if (!isNaN(num)) {
            indices.push(num);
          }
        }
      }
      return [...new Set(indices)].sort((a, b) => a - b);
    } catch (error) {
      console.error('Error parsing bond indices:', error);
      return [];
    }
  }
  public getMoleculeData(): void {
    if (!this.smilesInput.trim()) {
      return;
    }
    this.clearResults();
    const value = this.smilesInput.trim();
    if (value && !this.smilesHistory.includes(value)) {
      this.smilesHistory.unshift(value);
      if (this.smilesHistory.length > 10) {
        this.smilesHistory.pop();
      }
      this.saveSmilesHistory();
    }
    if (!isValidSmiles(this.smilesInput.trim(), this.RDKit)) {
      this.error = 'Invalid SMILES.';
      return;
    }
    this.loadingInfo = true;
    this.error = null;
    this.clearResults();
    const requestInfo: MoleculeInfoRequest = {
      smiles: this.smilesInput.trim(),
    };
    this.v1Service.v1PredictInfoCreate(requestInfo).subscribe({
      next: (response) => {
        if (!response) {
          this.error = 'No data received from the server';
          this.loadingInfo = false;
          return;
        }
        this.moleculeInfo = response.data ?? undefined;
        const svgData = response.data?.image_svg ?? '';
        this.svgImage = svgData;
        this.sanitizedSvg = sanitizeSvg(svgData, this.sanitizer);
        if (!this.svgImage && svgData) {
          console.log(
            'Empty or invalid SVG. Data received:',
            svgData.substring(0, 100),
          );
        }
        this.loadingInfo = false;
      },
      error: (error: any) => {
        this.error =
          'Error getting molecular information: ' +
          (error.message || 'Unknown error');
        this.loadingInfo = false;
      },
    });
  }
  public downloadSVGFile(useBdeResults?: boolean): void {
    let svgToDownload = this.svgImage;
    let filename = `molecular_structure_${this.smilesInput.replace(
      /[^a-zA-Z0-9]/g,
      '_',
    )}.svg`;
    if (useBdeResults && this.bdeResults?.image_svg) {
      svgToDownload = this.bdeResults.image_svg;
      filename = `bde_result_structure_${this.smilesInput.replace(
        /[^a-zA-Z0-9]/g,
        '_',
      )}.svg`;
    }
    if (!svgToDownload) {
      this.error = 'No hay imagen SVG disponible para descargar.';
      return;
    }
    let url: string | null = null;
    try {
      const blob = new Blob([svgToDownload], { type: 'image/svg+xml' });
      url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      this.error = null;
    } catch (error) {
      this.error = 'Error al descargar la imagen SVG.';
      console.error('Error downloading SVG:', error);
    } finally {
      if (url) window.URL.revokeObjectURL(url);
    }
  }
  public downloadPNGFile(useBdeResults?: boolean): void {
    let svgToDownload = this.svgImage;
    let filename = `molecular_structure_${this.smilesInput.replace(
      /[^a-zA-Z0-9]/g,
      '_',
    )}.png`;
    if (useBdeResults && this.bdeResults?.image_svg) {
      svgToDownload = this.bdeResults.image_svg;
      filename = `bde_result_structure_${this.smilesInput.replace(
        /[^a-zA-Z0-9]/g,
        '_',
      )}.png`;
    }
    if (!svgToDownload) {
      this.error = 'No SVG image available for download';
      return;
    }
    try {
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        this.error = 'Error creating canvas context';
        return;
      }
      const img = new Image();
      const svgBlob = new Blob([svgToDownload], {
        type: 'image/svg+xml;charset=utf-8',
      });
      const url = URL.createObjectURL(svgBlob);
      img.onload = () => {
        const scale = 2;
        canvas.width = img.width * scale;
        canvas.height = img.height * scale;
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = 'high';
        ctx.scale(scale, scale);
        ctx.fillStyle = 'white';
        ctx.fillRect(0, 0, img.width, img.height);
        ctx.drawImage(img, 0, 0);
        canvas.toBlob(
          (blob) => {
            if (blob) {
              const pngUrl = URL.createObjectURL(blob);
              const link = document.createElement('a');
              link.href = pngUrl;
              link.download = filename;
              document.body.appendChild(link);
              link.click();
              document.body.removeChild(link);
              URL.revokeObjectURL(pngUrl);
              URL.revokeObjectURL(url);
            } else {
              this.error = 'Error generating PNG image';
            }
          },
          'image/png',
          0.95,
        );
      };
      img.onerror = () => {
        this.error = 'Error loading SVG for conversion';
        URL.revokeObjectURL(url);
      };
      img.src = url;
    } catch (error) {
      this.error = 'Error converting SVG to PNG';
      console.error('Error converting to PNG:', error);
    }
  }
  public downloadSmilesData(): void {
    if (!this.bdeResults?.smiles_list) {
      this.error = 'No SMILES data available for download';
      return;
    }
    try {
      const smilesContent = this.bdeResults.smiles_list
        .filter((smiles) => smiles.trim() !== '')
        .join('\n');
      const blob = new Blob([smilesContent], { type: 'text/plain' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `bde_results_smiles_${this.smilesInput.replace(
        /[^a-zA-Z0-9]/g,
        '_',
      )}.txt`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      this.error = 'Error downloading SMILES data';
      console.error('Error downloading SMILES:', error);
    }
  }
  public downloadXyzData(): void {
    if (!this.bdeResults?.xyz_block) {
      this.error = 'No XYZ data available for download';
      return;
    }
    try {
      const blob = new Blob([this.bdeResults.xyz_block], {
        type: 'text/plain',
      });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `bde_results_xyz_${this.smilesInput.replace(
        /[^a-zA-Z0-9]/g,
        '_',
      )}.txt`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      this.error = 'Error downloading XYZ data';
      console.error('Error downloading XYZ:', error);
    }
  }
  public downloadBdeTableCSV(): void {
    if (!this.bdeResults?.bonds_predicted) {
      this.error = 'No BDE data available for download';
      return;
    }
    try {
      let csvContent =
        'Bond Index,Bond Atoms,Begin Atom,End Atom,BDE (kcal/mol),Bond Type\n';
      this.bdeResults.bonds_predicted.forEach((bond) => {
        const bdeValue = bond.bde !== null ? bond.bde.toFixed(2) : 'N/A';
        const bondType = bond.bond_type || 'Unknown';
        csvContent += `${bond.idx},"${bond.bond_atoms}",${bond.begin_atom_idx},${bond.end_atom_idx},${bdeValue},"${bondType}"\n`;
      });
      const blob = new Blob([csvContent], { type: 'text/csv' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `bde_results_table_${this.smilesInput.replace(
        /[^a-zA-Z0-9]/g,
        '_',
      )}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      this.error = 'Error downloading BDE table';
      console.error('Error downloading CSV:', error);
    }
  }
  public async downloadReports(format: 'smiles' | 'xyz'): Promise<void> {
    const zip = new JSZip();
    let hadAnyError = false;
    let blob: Blob | null = null;
    try {
      for (const result of this.allBDEResults) {
        const moleculeName = result.smiles || 'unknown';
        const fileName = `${moleculeName.replace(
          /[^a-zA-Z0-9]/g,
          '_',
        )}.${format}`;
        const content =
          format === 'smiles'
            ? result.smiles_list?.join('\n') || ''
            : result.xyz_block || '';
        if (!content) {
          hadAnyError = true;
          console.warn(`No data for ${fileName}`);
          continue;
        }
        zip.file(fileName, content);
      }
      blob = await zip.generateAsync({ type: 'blob' });
      saveAs(blob, `bde_reports_${format}.zip`);
      if (hadAnyError) {
        this.error = 'Some files had no data and were not included in the ZIP.';
      } else {
        this.error = null;
      }
    } catch (err) {
      this.error = 'Error generating or downloading the reports ZIP.';
      console.error('Error in downloadReports:', err);
    } finally {
    }
  }
  public toggleFullscreen(result: ExtendedFragmentResponseData): void {
    if (!result.zoomPan) result.zoomPan = createZoomPanState(1);
    result.zoomPan.isFullscreen = !result.zoomPan.isFullscreen;
    if (!result.zoomPan.isFullscreen) result.zoomPan.reset();
  }
  public zoomIn(result: ExtendedFragmentResponseData): void {
    if (!result.zoomPan) result.zoomPan = createZoomPanState(1);
    result.zoomPan.updateZoom(1.2);
  }
  public zoomOut(result: ExtendedFragmentResponseData): void {
    if (!result.zoomPan) result.zoomPan = createZoomPanState(1);
    result.zoomPan.updateZoom(1 / 1.2);
  }
  public resetZoom(result: ExtendedFragmentResponseData): void {
    if (!result.zoomPan) result.zoomPan = createZoomPanState(1);
    result.zoomPan.reset();
  }
  public onWheel(
    result: ExtendedFragmentResponseData,
    event: WheelEvent,
  ): void {
    if (!result.zoomPan) result.zoomPan = createZoomPanState(1);
    event.preventDefault();
    const delta = event.deltaY > 0 ? 0.9 : 1.1;
    result.zoomPan.updateZoom(delta);
  }
  public startPan(
    result: ExtendedFragmentResponseData,
    event: MouseEvent,
  ): void {
    if (!result.zoomPan) result.zoomPan = createZoomPanState(1);
    result.zoomPan.startPan(event);
  }
  public onPan(result: ExtendedFragmentResponseData, event: MouseEvent): void {
    if (!result.zoomPan) result.zoomPan = new ZoomPanState(1);
    result.zoomPan.onPan(event);
  }
  public endPan(result: ExtendedFragmentResponseData): void {
    if (!result.zoomPan) result.zoomPan = new ZoomPanState(1);
    result.zoomPan.endPan();
  }
  public downloadImage(result: ExtendedFragmentResponseData): void {
    const svgBlob = new Blob([result.image_svg], {
      type: 'image/svg+xml;charset=utf-8',
    });
    const url = URL.createObjectURL(svgBlob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${result.smiles || 'image'}.svg`;
    link.click();
    URL.revokeObjectURL(url);
  }
  public getTransform(result: ExtendedFragmentResponseData): string {
    if (!result.zoomPan) result.zoomPan = new ZoomPanState(1);
    return result.zoomPan.getTransform();
  }
  public showResults: boolean = false;
  public toggleResults(): void {
    this.showResults = !this.showResults;
  }
  public downloadSmiles(result: ExtendedFragmentResponseData): void {
    const blob = new Blob([result.smiles_list?.join('\n') || ''], {
      type: 'text/plain;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${result.smiles || 'result'}.txt`;
    link.click();
    URL.revokeObjectURL(url);
  }
  public downloadXyz(result: ExtendedFragmentResponseData): void {
    const blob = new Blob([result.xyz_block || ''], {
      type: 'text/plain;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${result.smiles || 'result'}.txt`;
    link.click();
    URL.revokeObjectURL(url);
  }
  // --- Filtering / duplicate removal for BDE tables ---
  private _hideNaBonds = true; // default checked
  public get hideNaBonds(): boolean {
    return this._hideNaBonds;
  }
  public set hideNaBonds(value: boolean) {
    this._hideNaBonds = value;
    this._filteredBondsCache = null; // Invalidate cache when filter changes
  }
  public removeDuplicatedAdjacent = true; // default checked
  // --- Sorting state ---
  public sortKey: 'idx' | 'bde' | 'bond_atoms' = 'idx';
  public sortDir: 1 | -1 = 1; // 1 asc, -1 desc

  public changeSort(key: 'idx' | 'bde' | 'bond_atoms'): void {
    if (this.sortKey === key) {
      this.sortDir = this.sortDir === 1 ? -1 : 1;
    } else {
      this.sortKey = key;
      this.sortDir = 1;
    }
  }
  public sortIndicator(key: 'idx' | 'bde' | 'bond_atoms'): string {
    if (this.sortKey !== key) return '□';
    return this.sortDir === 1 ? '▲' : '▼';
  }

  private sortBonds(bonds: PredictedBond[]): PredictedBond[] {
    const dir = this.sortDir;
    const key = this.sortKey;
    return [...bonds].sort((a, b) => {
      let av: any;
      let bv: any;
      switch (key) {
        case 'idx':
          av = a.idx;
          bv = b.idx;
          break;
        case 'bde':
          av = a.bde === null ? Number.POSITIVE_INFINITY : a.bde;
          bv = b.bde === null ? Number.POSITIVE_INFINITY : b.bde;
          break;
        case 'bond_atoms':
          av = a.bond_atoms || '';
          bv = b.bond_atoms || '';
          break;
      }
      if (av < bv) return -1 * dir;
      if (av > bv) return 1 * dir;
      return 0;
    });
  }

  private getHeavyAtomIndex(bond: PredictedBond): number | null {
    // Heuristic: if bond_atoms like X-H or H-X choose non-H atom index as heavy atom
    const atoms = bond.bond_atoms.split('-');
    if (atoms.length === 2) {
      const [a1, a2] = atoms;
      const a1IsH = a1.toUpperCase() === 'H';
      const a2IsH = a2.toUpperCase() === 'H';
      if (a1IsH && !a2IsH) return bond.end_atom_idx; // H-X => heavy is end
      if (a2IsH && !a1IsH) return bond.begin_atom_idx; // X-H => heavy is begin
    }
    // Fallback: return the smaller index for deterministic grouping
    return Math.min(bond.begin_atom_idx, bond.end_atom_idx);
  }

  private removeDuplicateEquivalentBonds(
    bonds: PredictedBond[],
  ): PredictedBond[] {
    if (!this.removeDuplicatedAdjacent) return bonds;
    const seen = new Set<string>();
    const result: PredictedBond[] = [];
    for (const bond of bonds) {
      const heavy = this.getHeavyAtomIndex(bond);
      const bdeKey = bond.bde !== null ? bond.bde.toFixed(2) : 'NA';
      const key = `${heavy}|${bond.bond_atoms}|${bdeKey}`;
      if (!seen.has(key)) {
        seen.add(key);
        result.push(bond);
      }
    }
    return result;
  }

  public get filteredBonds(): PredictedBondWithSource[] {
    // Return cached value if available and hideNaBonds hasn't changed
    if (this._filteredBondsCache !== null) {
      return this._filteredBondsCache;
    }

    if (!this.bdeResults?.bonds_predicted) return [];
    let bonds = this.bdeResults.bonds_predicted as PredictedBondWithSource[];
    // console.log('[FILTER] Original bonds from bdeResults:', bonds.slice(0, 3).map(b => ({ idx: b.idx, bde: b.bde, source: b.source })));
    if (this.hideNaBonds) bonds = bonds.filter((b) => b.bde !== null);
    bonds = this.removeDuplicateEquivalentBonds(
      bonds,
    ) as PredictedBondWithSource[];
    bonds = this.sortBonds(bonds) as PredictedBondWithSource[];
    // console.log('[FILTER] Final filtered bonds:', bonds.slice(0, 3).map(b => ({ idx: b.idx, bde: b.bde, source: b.source })));

    // Cache the result
    this._filteredBondsCache = bonds;
    return bonds;
  }

  public getFilteredBonds(
    result: ExtendedFragmentResponseData,
  ): PredictedBondWithSource[] {
    if (!result?.bonds_predicted) return [];
    let bonds = result.bonds_predicted as PredictedBondWithSource[];
    if (this.hideNaBonds) bonds = bonds.filter((b) => b.bde !== null);
    bonds = this.removeDuplicateEquivalentBonds(
      bonds,
    ) as PredictedBondWithSource[];
    bonds = this.sortBonds(bonds) as PredictedBondWithSource[];
    return bonds;
  }
}
