from abc import ABC, abstractmethod
import numpy as np
import cv2
from skimage.morphology import skeletonize as ski_skeletonize


class Access(type):

    __SENTINEL = object()

    def __new__(mcs, name, bases, class_dict):
        private = {
            key
            for base in bases
            for key, value in vars(base).items()
            if callable(value) and mcs.__is_final(value)
        }
        if any(key in private for key in class_dict):
            raise RuntimeError("certain methods may not be overridden")
        return super().__new__(mcs, name, bases, class_dict)

    @classmethod
    def __is_final(mcs, method):
        try:
            return method.__final is mcs.__SENTINEL
        except AttributeError:
            return False

    @classmethod
    def final(mcs, method):
        method.__final = mcs.__SENTINEL
        return method


class FingerRegionRecognizerTemplate(ABC):
    """
    The FingerReGionRecognizer template has few implemented functions and it declares the operations that all concrete
    FingerRegionRecognizers must implement.
    """
    def __init__(self, image) -> None:
        self.image = image
        self.gabor_img = None
        self.thin_image = None
        self.minutiae_weights_image = None
        self.mask = None

    def run_first_phase(self, image: cv2.typing.MatLike) -> cv2.typing.MatLike:
        """
        The FingerRegionRecognizer template method defines the skeleton of an algorithm.
        """
        self.first_step()
        self.second_step()
        self.third_step()
        return self.fifth_step()

    def run_second_phase(self) -> cv2.typing.MatLike:
        """
        The FingerRegionRecognizer template method defines the skeleton of an algorithm.
        """
        self.fifth_step()
        self.sixth_step()
        return self.seventh_step()

    @Access.final
    def run(self) -> cv2.typing.MatLike:
        """
        The FingerRegionRecognizer template method defines the skeleton of an algorithm.
        """
        self.first_step()
        self.second_step()
        self.third_step()
        self.fourth_step()
        self.fifth_step()
        self.sixth_step()
        return self.seventh_step()

    @abstractmethod
    def first_step(self) -> cv2.typing.MatLike:
        pass

    @abstractmethod
    def second_step(self) -> cv2.typing.MatLike:
        pass

    @abstractmethod
    def third_step(self) -> cv2.typing.MatLike:
        pass

    @abstractmethod
    def fourth_step(self) -> cv2.typing.MatLike:
        pass

    @Access.final
    def fifth_step(self) -> cv2.typing.MatLike:
        self.thin_image = self.__skeletonize(self.gabor_img)
        return self.thin_image

    @Access.final
    def sixth_step(self) -> cv2.typing.MatLike:
        self.minutiae_weights_image = self.__calculate_minutiae_weights(self.thin_image)
        return self.minutiae_weights_image

    @Access.final
    def seventh_step(self) -> cv2.typing.MatLike:
        block_size = 15
        best_region = self.__get_best_region(
            self.thin_image, self.minutiae_weights_image, block_size, self.mask
        )
        result_image = self.__draw_ridges_count_on_region(
            best_region, self.image, self.thin_image, block_size
        )
        return result_image

    def __skeletonize(self, img):
        binary_image = np.zeros_like(img)
        binary_image[img == 0] = 1.0

        skeleton = ski_skeletonize(binary_image)

        output_img = (1 - skeleton) * 255.0
        return output_img.astype(np.uint8)

    def __detect_minutiae(self, image, row, col):
        if image[row][col] == 1:
            kernel = [
                (-1, -1),
                (-1, 0),
                (-1, 1),
                (0, 1),
                (1, 1),
                (1, 0),
                (1, -1),
                (0, -1),
                (-1, -1),
            ]
            values = []
            for k, l in kernel:
                values.append(image[row + l][col + k])
            crossings = (
                sum(abs(values[k] - values[k + 1]) for k in range(len(values) - 1)) // 2
            )
            if crossings == 1:
                return "termination"
            if crossings == 3:
                return "bifurcation"
        return "none"

    def __calculate_minutiae_weights(self, image):
        binary_image = (image == 0).astype(np.int8)
        minutiae_weights_array = np.zeros_like(image, dtype=np.float_)

        for col in range(1, image.shape[1] - 1):
            for row in range(1, image.shape[0] - 1):
                minutiae = self.__detect_minutiae(binary_image, row, col)
                if minutiae == "bifurcation":
                    minutiae_weights_array[row, col] += 1.0
                elif minutiae == "termination":
                    minutiae_weights_array[row, col] += 2.0

        return minutiae_weights_array

    def __count_lines(self, image):
        kernel = np.ones((3, 3), dtype=np.uint8)
        eroded_image = cv2.erode(image, kernel)
        binary_image = cv2.threshold(eroded_image, 127, 255, cv2.THRESH_BINARY)[1]
        main_diagonal = self.__count_diagonal_lines(binary_image)
        secondary_diagonal = self.__count_diagonal_lines(np.fliplr(binary_image))
        return (
            (secondary_diagonal, "secondary_diagonal")
            if main_diagonal <= secondary_diagonal
            else (main_diagonal, "main_diagonal")
        )

    def __count_diagonal_lines(self, image):
        is_white = True
        counter = 0
        for i in range(image.shape[0]):
            if image[i][i] == 0 and is_white:
                counter += 1
                is_white = False
            if image[i][i] == 255:
                is_white = True
        return counter

    def __draw_diagonal(
        self,
        image,
        start_i,
        start_j,
        end_i,
        end_j,
        line_count,
        block_size,
        text_y,
        text_x,
        color,
    ):
        cv2.line(image, (start_j, start_i), (end_j, end_i), (0, 0, 255), 1)
        cv2.putText(
            image,
            f" {line_count}",
            (text_y, text_x - block_size),
            cv2.FONT_HERSHEY_TRIPLEX,
            0.5,
            color,
            1,
        )
        cv2.putText(
            image, "ridges", (text_y, text_x), cv2.FONT_HERSHEY_TRIPLEX, 0.5, color, 1
        )

    def __get_best_region(self, thin_image, minutiae_weights_image, block_size, mask):
        best_region = None
        block_minutiaes_weight = float("inf")
        rows, cols = thin_image.shape
        shape_block = block_size * 8
        window = (shape_block // block_size) - 1
        for col in range(1, cols - window):
            for row in range(1, rows - window):
                mask_slice = mask[
                    col * block_size : col * block_size + shape_block,
                    row * block_size : row * block_size + shape_block,
                ]
                mask_flag = np.sum(mask_slice)
                if mask_flag == shape_block * shape_block:
                    number_vision_problems = np.sum(
                        minutiae_weights_image[
                            col * block_size : col * block_size + shape_block,
                            row * block_size : row * block_size + shape_block,
                        ]
                    )
                    if number_vision_problems <= block_minutiaes_weight:
                        block_minutiaes_weight = number_vision_problems
                        best_region = [
                            col * block_size,
                            col * block_size + shape_block,
                            row * block_size,
                            row * block_size + shape_block,
                        ]
        if best_region:
            return best_region

    def __draw_ridges_count_on_region(
        self, region, input_image, thin_image, block_size
    ):
        output_image = cv2.cvtColor(input_image.copy(), cv2.COLOR_GRAY2RGB)
        if region is None:
            return output_image
        region_copy = (thin_image[region[0] : region[1], region[2] : region[3]]).copy()
        line_count, line_type = self.__count_lines(region_copy)
        text_y = (region[3] - region[2]) // 2 + region[2]
        if line_type == "main_diagonal":
            text_x = (region[1] - region[0]) // 3 + region[0]
            self.__draw_diagonal(
                output_image,
                region[0],
                region[2],
                region[1],
                region[3],
                line_count,
                block_size,
                text_y,
                text_x,
                (0, 255, 255),
            )
        elif line_type == "secondary_diagonal":
            text_x = 2 * (region[1] - region[0]) // 3 + region[0]
            self.__draw_diagonal(
                output_image,
                region[0],
                region[3],
                region[1],
                region[2],
                line_count,
                block_size,
                text_y,
                text_x,
                (0, 255, 255),
            )
        cv2.rectangle(
            output_image, (region[2], region[0]), (region[3], region[1]), (0, 0, 255), 1
        )
        return output_image
