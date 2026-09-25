import { Component, OnInit } from '@angular/core';
import { NgParticlesService, NgxParticlesModule } from '@tsparticles/angular';
import { loadSlim } from '@tsparticles/slim';

@Component({
  selector: 'app-particles-background',
  standalone: true,
  imports: [NgxParticlesModule],
  templateUrl: './particles-background.component.html',
  styleUrls: ['./particles-background.component.scss'],
})
export class ParticlesBackgroundComponent implements OnInit {
  // id usado por el componente
  id = 'tsparticles';

  // Opciones para las partículas. Se usa "resize: { enable: true }" para evitar errores de typescript.
  // Si prefieres tiparlas, puedes importAR RecursivePartial<IOptions> desde tu engine instalado y castear.
  particlesOptions = {
    background: { color: { value: '#071029' } },
    fpsLimit: 60,
    interactivity: {
      events: {
        onClick: { enable: true, mode: 'push' },
        onHover: { enable: true, mode: 'repulse' },
        resize: { enable: true }, // <-- forma correcta para TS
      },
      modes: {
        push: { quantity: 4 },
        repulse: { distance: 100, duration: 0.4 },
      },
    },
    particles: {
      number: { value: 160, density: { enable: true, area: 800 } },
      color: { value: '#ffffff' },
      links: {
        enable: true,
        distance: 140,
        color: '#9fb3c8',
        opacity: 0.35,
        width: 1,
      },
      move: { enable: true, speed: 2, outModes: { default: 'bounce' } },
      size: { value: { min: 1, max: 4 } },
      opacity: { value: 0.75 },
    },
    detectRetina: true,
  } as any; // as any evita problemas de tipado estricto; puedes reemplazar por RecursivePartial<IOptions>

  constructor(private readonly ngParticlesService: NgParticlesService) {}

  ngOnInit(): void {
    // Inicializa el engine y carga las features "slim"
    this.ngParticlesService.init(async (engine: any) => {
      await loadSlim(engine);
    });
  }

  // callback opcional cuando el container esté listo
  particlesLoaded(container: any): void {
    // console.log('Particles container loaded', container);
  }
}
