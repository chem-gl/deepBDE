// Entorno de desarrollo (build por defecto de `ng serve`).
export const environment = {
  production: false,
  // Backend Django local. El cliente generado ya prefixea las rutas con /api/v1,
  // asi que aqui solo va el origin.
  apiBasePath: 'http://localhost:8000',
};
