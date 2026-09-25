import { Routes } from '@angular/router';
import { AboutComponent } from './pages/about/about.component';
import { CitationComponent } from './pages/citation/citation.component';
import { HomeComponent } from './pages/home/home.component';

export const routes: Routes = [
  { path: '', component: HomeComponent },
  { path: 'about', component: AboutComponent },
  { path: 'citation', component: CitationComponent },
  { path: '**', redirectTo: '' },
];
