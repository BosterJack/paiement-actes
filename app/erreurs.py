"""Erreurs métier et format unique des réponses d'erreur : {"detail": "..."}."""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("erreurs")


class ErreurMetier(Exception):
    """Règle de gestion non respectée ; les services la lèvent, l'API la traduit en HTTP."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def installer_gestionnaires(app: FastAPI) -> None:
    @app.exception_handler(ErreurMetier)
    async def erreur_metier(request: Request, exc: ErreurMetier):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.exception_handler(Exception)
    async def erreur_inattendue(request: Request, exc: Exception):
        # Trace complète dans les journaux, aucun détail technique renvoyé au client.
        log.exception("Erreur inattendue sur %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Erreur interne, veuillez réessayer"})
