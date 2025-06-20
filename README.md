# SpectrumX Theme

A responsive and accessible HTML/CSS theme for the SpectrumX project. This theme provides a set of reusable templates and components, built on the Bootstrap 5 framework and designed to be compliant with WCAG 2.2 Level AA standards.

## Features

*   **Fully Responsive**: Built with Bootstrap 5 to ensure a seamless experience on all devices, from mobile phones to desktop screens.
*   **WCAG 2.2 AA Compliant**: Meticulously designed and audited for accessibility, with high-contrast colors, visible focus indicators, ARIA support, and more. See the [WCAG 2.2 AA Compliance Report](WCAG_2.2_AA_Compliance_Report.md) for full details.
*   **Multiple Page Templates**: Includes several pre-built page layouts:
    *   `index.html`: A welcoming home page.
    *   `typography.html`: A demonstration of all standard typography elements.
    *   `components.html`: Showcases advanced, custom-built components.
    *   `forms.html`: A comprehensive collection of form elements and layouts.
    *   `layout.html`: An example of the basic page structure.
    *   `search.html`: A functional search results page.
*   **Advanced Components**:
    *   **File Browser**: An accessible file browser with full keyboard navigation (arrow keys, Enter, Space), folder expansion, multi-select with cascading selection, and context-aware action buttons (Rename, Delete, Add Subfolder, View Metadata).
    *   **Sortable & Paginated Table**: The search results table allows for client-side sorting by column and includes a dynamic pagination component.
    *   **Custom Forms**: Includes examples of standard and compact form layouts with robust, JavaScript-based validation.
    *   **Range Sliders**: Styled examples of both single-handle native sliders and dual-handle `noUiSlider` instances.

## Getting Started

To use this theme, simply clone the repository or download the files.

```bash
git clone https://github.com/your-username/spx-theme.git
```

Navigate to the project directory and open any of the `.html` files in your web browser to view the pages.

```bash
cd spx-theme
# On macOS
open index.html
# On Windows
start index.html
# On Linux
xdg-open index.html
```

## Customization

The theme is designed to be easily customizable.

*   **Colors & Styling**: All custom styles, including the primary color palette and component designs, are located in `css/style.css`. Key theme colors can be changed by modifying the CSS variables at the top of the file or in the `.btn-primary` and `.pagination` rules.
*   **Fonts**: The theme uses the 'Roboto' font from Google Fonts, which is linked in the `<head>` of each HTML file. This can be changed to any other web font.
*   **Navigation**: The main navigation bar is defined in each `.html` file. To add, remove, or change links, you will need to edit the `<nav>` element on each page.
*   **Content**: Page content is located within the `<main>` element of each HTML file.

## File Structure

```
spx-theme/
├── css/
│   └── style.css           # All custom styles
├── images/
│   ├── Logo.png            # Main combined logo
│   └── ...                 # Other image assets
├── js/
│   └── components.js       # JavaScript for the file browser
├── *.html                  # All page templates
├── WCAG_2.2_AA_Compliance_Report.md # Detailed accessibility report
└── README.md               # This file
```

## Acknowledgements

This theme was developed as part of the NSF SpectrumX project, an NSF Spectrum Innovation Center funded via Award 2132700 and operated under a cooperative agreement by the University of Notre Dame. 