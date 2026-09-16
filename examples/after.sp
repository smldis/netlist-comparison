* Rename, add a container, change a raw width and a shared default.
.model N NMOS
.subckt RENAMED IN OUT VSS W=5u
C9 T VSS 1p
R9 OUT VSS 1k
M9 T IN VSS VSS N W=3u L=1u
M8 OUT IN T VSS N W=6u L=1u
.ends RENAMED
.subckt INNER IN OUT G
XNEW IN OUT G RENAMED W=4u
.ends INNER
.subckt WRAP IN OUT G
XCORE IN OUT G INNER
.ends WRAP
XMOVED in out 0 WRAP
