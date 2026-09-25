export * from './schema.service';
import { SchemaService } from './schema.service';
export * from './v1.service';
import { V1Service } from './v1.service';
export const APIS = [SchemaService, V1Service];
