# VC Data Room — PDF generation
# Requires: pandoc + a PDF engine (weasyprint or wkhtmltopdf or xelatex)
#
# Usage:
#   make pdf              # all .md -> .pdf
#   make architecture     # Steloom_Architecture.pdf only
#   make quality          # Steloom_AI_Quality_and_Limitations.pdf only
#   make product          # Steloom_Product_Overview.pdf only
#   make clean            # remove generated PDFs

PANDOC      ?= pandoc
PDF_ENGINE  ?= weasyprint
OUTDIR      ?= dist

MD_FILES    := $(wildcard *.md)
PDF_FILES   := $(patsubst %.md,$(OUTDIR)/%.pdf,$(MD_FILES))

PANDOC_OPTS := \
	--from markdown+pipe_tables+footnotes \
	--pdf-engine=$(PDF_ENGINE) \
	--toc --toc-depth=2 \
	--metadata title-prefix="Steloom — " \
	-V geometry:margin=2cm \
	-V fontsize=10pt \
	-V colorlinks=true

.PHONY: all pdf architecture quality product clean

all: pdf

pdf: $(PDF_FILES)

$(OUTDIR)/%.pdf: %.md | $(OUTDIR)
	$(PANDOC) $(PANDOC_OPTS) -o $@ $<

architecture: $(OUTDIR)/Steloom_Architecture.pdf
quality:      $(OUTDIR)/Steloom_AI_Quality_and_Limitations.pdf
product:      $(OUTDIR)/Steloom_Product_Overview.pdf

$(OUTDIR):
	mkdir -p $(OUTDIR)

clean:
	rm -rf $(OUTDIR)
