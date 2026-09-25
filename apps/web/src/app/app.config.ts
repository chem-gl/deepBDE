// src/app/app.config.ts
import { provideHttpClient } from '@angular/common/http';
import {
  ApplicationConfig,
  importProvidersFrom,
  provideBrowserGlobalErrorListeners,
  provideZoneChangeDetection,
} from '@angular/core';
import { provideRouter } from '@angular/router';
import { Configuration } from '../../angular-client';
import { ApiModule } from '../../angular-client/api.module';
import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes),
    provideHttpClient(),
    importProvidersFrom(
      ApiModule.forRoot(
        () =>
          new Configuration({
            basePath: 'https://test1.guzman-lopez.com', // Cambia por tu URL real
          })
      )
    ),
  ],
};
