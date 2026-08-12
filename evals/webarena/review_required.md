# Human review log

No blocking review items currently.

The workflow freeze uses commit `590beea`, the last pre-cross-template routing implementation. Its
distiller produces a complete parameterized standalone workflow and may create private helper
functions inside that file. Those helpers are not the separately retrieved v4 site primitive
package and do not violate arm isolation.
