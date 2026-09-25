// Entorno de produccion (aplicado via fileReplacements en angular.json).
// Same-origin: nginx sirve la SPA y hace proxy de /api/ hacia el backend,
// y el cliente generado ya incluye /api/v1 en cada path -> basta ''.
export const environment = {
  production: true,
  apiBasePath: '',
};
