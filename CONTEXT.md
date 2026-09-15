# CUBRID Configuration

A searchable view of CUBRID configuration parameters and their values.

## Language

**Parameter**:
A named CUBRID setting, such as `enable_string_compression`, whose value controls CUBRID behavior.
_Avoid_: Conf (ambiguous between a parameter and a configuration file).

**Hidden parameter**:
A CUBRID parameter omitted from ordinary parameter listings, but intended to be discoverable in this tool.

**Default difference**:
A difference between a parameter's displayed current value and its displayed default value, marked with `*` by paramdump in the inspected CUBRID build. This does not establish whether the configuration file explicitly sets the parameter.

**Client value**:
The parameter value observed in the client process used for the parameter dump, identified by `C`.

**Server value**:
The parameter value obtained from the database server for the parameter dump, identified by `S`.

**Editing target**:
The configuration file and section to which an edit is saved. The selected target remains visible while browsing and editing parameters.

**Database override**:
A parameter assignment in a database-specific section that takes precedence over the common assignment for that database.

**Configured value**:
The value explicitly assigned to a parameter in the editing target. It can differ from the observed client or server value.

**Remove override**:
Removal of a parameter's explicit common assignment, allowing other applicable configuration and defaults to determine its value. It does not mean assigning the compiled default explicitly.

**Limited validation**:
A validation result where basic input checks pass but some parameter-specific constraints are unknown. Saving is permitted without claiming that CUBRID will accept the value.

**Offline catalog**:
The available parameter names and metadata obtained without opening or connecting to a database. It does not contain observed live client or server values.

**Limited offline editing**:
Editing existing configured settings when a complete offline catalog and live parameter dump are unavailable. Missing settings and metadata are not inferred.
