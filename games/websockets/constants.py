from enum import IntEnum


class WSErrorCodes(IntEnum):
    # Codigos de errores utilizados en los Websockets.
    # Rango 4000-4999
    GENERIC_ERROR = 4000
    INVALID_JSON = 4001
    UNAUTHENTICATED = 4002
    GAME_NOT_FOUND = 4003
    REPEATED_PLAYER = 4004
    INVALID_GAME = 4005
    WRONG_TURN = 4006
    ILLEGAL_MOVE = 4007


class StockfishErrorCodes(IntEnum):
    GENERIC_ERROR = 4000
