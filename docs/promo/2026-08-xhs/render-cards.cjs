const fs = require('fs');
const path = require('path');
const sharp = require('sharp');

const dir = __dirname;
const cards = [
  ['00-cover.svg', '00-cover.png'],
  ['01-why-it-matters.svg', '01-why-it-matters.png'],
  ['02-proof.svg', '02-proof.png'],
  ['03-figure-proof.svg', '03-figure-proof.png'],
];

(async () => {
  for (const [source, target] of cards) {
    let svgText = fs.readFileSync(path.join(dir, source), 'utf8');
    svgText = svgText.replace(/href="([^"#]+\.(?:png|jpe?g|webp))"/gi, (match, href) => {
      const imagePath = path.resolve(dir, href);
      const extension = path.extname(imagePath).slice(1).toLowerCase();
      const mime = extension === 'jpg' || extension === 'jpeg' ? 'image/jpeg' : `image/${extension}`;
      const encoded = fs.readFileSync(imagePath).toString('base64');
      return `href="data:${mime};base64,${encoded}"`;
    });
    const svg = Buffer.from(svgText);
    await sharp(svg, { density: 192 })
      .resize(2484, 3312, { fit: 'fill' })
      .png({ compressionLevel: 9, adaptiveFiltering: true })
      .toFile(path.join(dir, target));
    console.log(target);
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
