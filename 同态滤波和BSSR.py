###############################################################同态滤波
# import numpy as np
# from astropy.io import fits
# from skimage import exposure
# import matplotlib.pyplot as plt

# def normalize_and_stretch(image_data):
#     """改进的归一化拉伸函数"""
#     p2, p98 = np.percentile(image_data, (2, 98))
#     stretched = exposure.rescale_intensity(
#         image_data, in_range=(p2, p98), out_range=(0, 1)
#     )
#     return stretched

# def restore_grayscale(original_float, processed, original_min, original_max):
#     """灰度值恢复函数（更新版）"""
#     bg_mask = original_float < np.percentile(original_float, 50)
#     original_bg_mean = np.mean(original_float[bg_mask])
#     original_bg_std = np.std(original_float[bg_mask])
    
#     processed_bg_mean = np.mean(processed[bg_mask])
    
#     scale = original_bg_std / np.std(processed[bg_mask])
#     offset = original_bg_mean - processed_bg_mean * scale
    
#     restored = processed * scale + offset
#     restored = np.clip(restored, original_min, original_max)  # 使用原始整数范围
#     return restored

# def homomorphic_filter(image, gamma_low=0.2, gamma_high=3.5, cutoff=50, c=0.5):
#     """同态滤波函数（参数说明已整合到函数文档中）""" 
#     # [原有滤波实现保持不变...]
#     # 对数变换（避免零值）
#     log_image = np.log(image + 1e-6)
    
#     # 傅里叶变换
#     fft_image = np.fft.fft2(log_image)
#     fft_shift = np.fft.fftshift(fft_image)
    
#     # 创建高斯滤波器
#     rows, cols = image.shape
#     x = np.linspace(-cols/2, cols/2, cols)
#     y = np.linspace(-rows/2, rows/2, rows)
#     xx, yy = np.meshgrid(x, y)
#     distance_sq = xx**2 + yy**2
    
#     # 构造滤波器
#     H = (gamma_high - gamma_low) * (1 - np.exp(-c * distance_sq/(cutoff**2))) + gamma_low
    
#     # 应用滤波器
#     filtered_shift = fft_shift * H
    
#     # 逆傅里叶变换
#     fft_ishift = np.fft.ifftshift(filtered_shift)
#     img_back = np.fft.ifft2(fft_ishift)
#     img_back = np.abs(img_back)
    
#     # 指数变换
#     filtered_image = np.exp(img_back) - 1e-6
#     return filtered_image

# # 读取FITS文件并保留原始数据类型
# input_path = "F:/astronomers___image/15I/20231115SS-001I-20s.fit"
# with fits.open(input_path) as hdul:
#     original_data_int = hdul[0].data  # 原始整数数据
#     original_min = original_data_int.min()
#     original_max = original_data_int.max()
#     data = original_data_int.astype(np.float32)  # 转换为float处理
#     header = hdul[0].header

# # 执行同态滤波
# filtered_data = homomorphic_filter(data)

# # 灰度值恢复（使用原始整数范围）
# restored_data = restore_grayscale(data, filtered_data, original_min, original_max)

# # 四舍五入并转换为原始整数类型
# restored_data_int = np.round(restored_data).astype(original_data_int.dtype)

# # 保存处理后的FITS文件
# output_fits = "F:/output_filters/output.fit"
# fits.writeto(output_fits, restored_data_int, header, overwrite=True)

# # 归一化拉伸并保存PNG（保持不变）
# stretched = normalize_and_stretch(restored_data_int.astype(np.float32))
# output_png = "F:/output_filters/output.png"

# fig = plt.figure(frameon=False)
# fig.set_size_inches(restored_data_int.shape[1]/500, restored_data_int.shape[0]/500)
# ax = plt.Axes(fig, [0., 0., 1., 1.])
# ax.set_axis_off()
# fig.add_axes(ax)
# ax.imshow(stretched, cmap='gray', aspect='auto')
# fig.savefig(output_png, dpi=500, bbox_inches='tight', pad_inches=0)
# plt.close()

##############################################################################retinex（BFR）
import os
import cv2
import numpy as np
from astropy.io import fits
from skimage import exposure
import matplotlib.pyplot as plt

def normalize_and_stretch(image_data):
    """改进的归一化拉伸函数"""
    # 使用更鲁棒的百分位拉伸
    p2, p98 = np.percentile(image_data, (2, 99))
    stretched = exposure.rescale_intensity(
        image_data, in_range=(p2, p98), out_range=(0, 1)
    )
    return stretched

def bilateral_retinex_decompose(image, d):

    image_normalized = (image / 65535).astype(np.float32)

    log_image = np.log1p(image_normalized)

    bilateral_filtered_image = cv2.bilateralFilter(log_image, d, 120, 120)

    detail_image = log_image - bilateral_filtered_image

    detail_image_exp = np.expm1(detail_image)

    bilateral_filtered_image_exp = np.expm1(bilateral_filtered_image)

    detail_image_normalized = cv2.normalize(detail_image_exp, None, 0, 1, cv2.NORM_MINMAX)
    bilateral_filtered_image_normalized = cv2.normalize(bilateral_filtered_image_exp, None, 0, 1, cv2.NORM_MINMAX)

    reflectance = np.clip(detail_image_normalized * 65535, 0, 65535).astype(np.uint16)
    illumination = np.clip(bilateral_filtered_image_normalized * 65535, 0, 65535).astype(np.uint16)

    return reflectance,illumination

def process_retinex(input_path, output_dir='D:/output_filters/', d=15):
    # 读取 FITS 数据和头信息
    data = fits.getdata(input_path)
    header = fits.getheader(input_path)

    # 创建输出目录（若不存在）
    os.makedirs(output_dir, exist_ok=True)

    # 执行 Retinex 分解
    reflectance, illumination = bilateral_retinex_decompose(data, d)
    final_image_B = cv2.GaussianBlur(reflectance, (9,9), 0)

    # 保存 FITS 文件（附带原始 Header）
    fits.writeto(os.path.join(output_dir, 'reflectance.fit'),
                 reflectance.astype(np.uint16), header=header, overwrite=True)
    fits.writeto(os.path.join(output_dir, 'illumination.fit'),
                 illumination.astype(np.uint16), header=header, overwrite=True)
    fits.writeto(os.path.join(output_dir, 'final_image_B.fit'),
                 final_image_B.astype(np.uint16), header=header, overwrite=True)

    # 保存 PNG 文件
    for name, component in [('reflectance', reflectance), ('illumination', illumination), ('final_image_B', final_image_B)]:
        stretched = normalize_and_stretch(component)
        plt.imsave(os.path.join(output_dir, f'{name}.png'), stretched, cmap='gray', dpi=500)

    print(f"处理完成，文件已保存至：{output_dir}")


# 使用示例
process_retinex(
    input_path='D:/20201113U0-001I.fit',
    d=15
)
