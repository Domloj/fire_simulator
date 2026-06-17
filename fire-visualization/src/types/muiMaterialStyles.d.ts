export * from '@mui/material/styles';

declare module '@mui/material/styles' {
  interface CustomShadows {
    button?: string;
    text?: string;
    z1?: string;
  }
  interface Theme {
    customShadows?: CustomShadows;
  }

  interface PaletteColor {
    lighter?: string;
    100?: string;
    200?: string;
    400?: string;
    600?: string;
    700?: string;
    800?: string;
    darker?: string;
    900?: string;
    A100?: string;
    A200?: string;
    A300?: string;
  }

  interface SimplePaletteColorOptions {
    lighter?: string;
    100?: string;
    200?: string;
    400?: string;
    600?: string;
    700?: string;
    800?: string;
    darker?: string;
    900?: string;
    A100?: string;
    A200?: string;
    A300?: string;
  }
}
