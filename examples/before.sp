* Small structural example, not a simulated design.
.model N NMOS
.subckt CELL IN OUT VSS W=2u
M1 OUT IN T VSS N W=W L=1u
M2 T IN VSS VSS N W=3u L=1u
R1 OUT VSS 1k
C1 T VSS 1p
.ends CELL
.subckt WRAP IN OUT G
XCH IN OUT G CELL W=4u
.ends WRAP
XOLD in out 0 WRAP
