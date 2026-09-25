import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { RouterModule } from '@angular/router';

@Component({
  selector: 'app-navbar',
  standalone: true,
  imports: [CommonModule, RouterModule],
  template: `
    <nav class="navbar">
      <div class="navbar-container">
        <div class="navbar-brand">
          <a routerLink="/" class="brand-link">
            <span class="brand-text">DeepBDE</span>
          </a>
        </div>
        <div class="navbar-menu">
          <a
            routerLink="/"
            routerLinkActive="active"
            [routerLinkActiveOptions]="{ exact: true }"
            class="nav-link"
          >
            🏠 Home
          </a>
          <a routerLink="/about" routerLinkActive="active" class="nav-link">
            ℹ️ About
          </a>
          <a routerLink="/citation" routerLinkActive="active" class="nav-link">
            📄 Citation
          </a>
        </div>
      </div>
    </nav>
  `,
  styleUrls: ['./navbar.component.scss'],
})
export class NavbarComponent {}
