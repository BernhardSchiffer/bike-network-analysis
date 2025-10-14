from typing import TypeAlias

NodeId: TypeAlias = int | str
EdgeId: TypeAlias = tuple[NodeId, NodeId, NodeId]
Route: TypeAlias = list[NodeId]
BikeId: TypeAlias = str

type LEFT = 'LEFT'
type STRAIGHT = 'STRAIGHT'
type RIGHT = 'RIGHT'
type U_TURN = 'U_TURN'
type TurnDirection = LEFT | STRAIGHT | RIGHT | U_TURN
