import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';

@Component({
  selector: 'app-citation',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './citation.component.html',
  styleUrls: ['./citation.component.scss'],
})
export class CitationComponent {
  academicCitation = ` Paper in preparation: DeepBDE, a graph neural network for fast and accurate bond dissociation enthalpies
Authors: [To be updated with actual authors]
Journal: [To be updated with publication details]
Year: 2024
DOI: [To be updated]`;

  bibtexCitation = `@article{deepbde2024,
  title={Paper in preparation: DeepBDE, a graph neural network for fast and accurate bond dissociation enthalpies},
  author={[To be updated with actual authors]},
  journal={[To be updated with journal name]},
  year={2024},
  doi={[To be updated]},
  url={https://github.com/MSRG/DeepBDE/}
}`;

  copyMessage = '';

  copyToClipboard(text: string) {
    navigator.clipboard
      .writeText(text)
      .then(() => {
        this.copyMessage = '✅ Copied to clipboard!';
        setTimeout(() => {
          this.copyMessage = '';
        }, 3000);
      })
      .catch(() => {
        this.copyMessage = '❌ Failed to copy';
        setTimeout(() => {
          this.copyMessage = '';
        }, 3000);
      });
  }
}
