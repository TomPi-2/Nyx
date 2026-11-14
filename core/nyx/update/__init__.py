"""Actualizaciones automáticas, la parte del núcleo (SPEC §15; tarea 9.05).

La descarga, el cambio de versión y la vuelta atrás los hace Velopack desde la app (9.06). El
núcleo decide cuándo es buen momento, guarda una copia de los datos antes de cambiar y aplica
las migraciones de la versión nueva al arrancar (si una falla, restaura la copia).
"""
