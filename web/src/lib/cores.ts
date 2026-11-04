/** Cores para marcar pets e pessoas (a mesma ordem da paleta de gráficos, validada para daltonismo). */
export const PALETA = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948']

/** Sem cor escolhida: pets pegam a paleta de frente para trás e pessoas de trás para frente (em ordem de nome); o programa de casa usa a mesma regra. */
export const corPadraoPet = (i: number) => PALETA[i % PALETA.length]
export const corPadraoPessoa = (j: number) => PALETA[PALETA.length - 1 - (j % PALETA.length)]

export const corValida = (c: string | null | undefined): c is string => !!c && /^#[0-9a-f]{6}$/i.test(c)
