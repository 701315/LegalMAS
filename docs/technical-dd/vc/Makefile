# VC Data Room — PDF generation (compact profile, tables, mermaid PNG)
# Requires: pandoc + weasyprint + mmdc (@mermaid-js/mermaid-cli)
#
# Usage:
#   make pdf              # all .md -> .pdf
#   make architecture     # Steloom_Architecture.pdf only
#   make quality          # Steloom_AI_Quality_and_Limitations.pdf only
#   make product          # Steloom_Product_Overview.pdf only
#   make clean            # remove generated PDFs and diagram PNGs

PANDOC      ?= pandoc
PDF_ENGINE  ?= weasyprint
OUTDIR      ?= dist

MD_FILES    := $(wildcard *.md)
PDF_FILES   := $(patsubst %.md,$(OUTDIR)/%.pdf,$(MD_FILES))

PANDOC_OPTS := \
	--from markdown+pipe_tables+footnotes \
	--pdf-engine=$(PDF_ENGINE) \
	--css=_pdf.css \
	--resource-path=.

.PHONY: all pdf architecture quality product clean

all: pdf

pdf: $(PDF_FILES)

$(OUTDIR)/%.pdf: %.md _pdf.css | $(OUTDIR) $(OUTDIR)/diagrams
	@echo "=== Rendering mermaid blocks in $< ==="
	@python3 render_mermaid.py "$<" "$(OUTDIR)/diagrams" > "$<.full.md"
	@echo "=== Generating $@ ==="
	$(PANDOC) $(PANDOC_OPTS) \
	  --metadata title="$(shell head -1 $< | sed 's/^# //')" \
	  -o $@ "$<.full.md"
	@rm -f "$<.full.md"

architecture: $(OUTDIR)/Steloom_Architecture.pdf
quality:      $(OUTDIR)/Steloom_AI_Quality_and_Limitations.pdf
product:      $(OUTDIR)/Steloom_Product_Overview.pdf

$(OUTDIR):
	mkdir -p $(OUTDIR)

$(OUTDIR)/diagrams:
	mkdir -p $(OUTDIR)/diagrams

clean:
	rm -rf $(OUTDIR)
